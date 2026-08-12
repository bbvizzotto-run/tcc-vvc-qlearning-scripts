"""Importa pacotes DASH locais para o manifesto medido do simulador.

O módulo usa somente a biblioteca padrão e cobre os modos de endereçamento
mais comuns em pacotes DVB-DASH estáticos: ``SegmentTemplate`` (com duração
fixa ou ``SegmentTimeline``), ``SegmentList`` e ``SegmentBase`` com índice
``sidx`` em um arquivo ISO-BMFF único.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from segment_manifest import SegmentManifest, load_segment_manifest


DVB_VVC_SOURCE_URL = (
    "https://dvb.org/specifications/verification-validation/vvc-test-content/"
)
MANIFEST_COLUMNS: tuple[str, ...] = (
    "sequence",
    "segment",
    "bitrate_kbps",
    "duration_s",
    "size_bytes",
    "psnr_y_db",
    "source_file",
    "sha256",
)
ISO_DURATION_PATTERN = re.compile(
    r"^P(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)
TEMPLATE_TOKEN_PATTERN = re.compile(
    r"\$\$|\$(RepresentationID|Number|Bandwidth|Time)(%0\d+d)?\$"
)


@dataclass(frozen=True)
class DashSegment:
    """Um segmento de mídia resolvido no pacote local."""

    path: Path
    duration_s: float
    byte_start: int | None = None
    size_bytes: int | None = None

    def __post_init__(self) -> None:
        if self.duration_s <= 0 or not math.isfinite(self.duration_s):
            raise ValueError("a duração do segmento deve ser positiva e finita")
        if (self.byte_start is None) != (self.size_bytes is None):
            raise ValueError("byte_start e size_bytes devem ser usados juntos")
        if self.byte_start is not None and self.byte_start < 0:
            raise ValueError("byte_start não pode ser negativo")
        if self.size_bytes is not None and self.size_bytes <= 0:
            raise ValueError("size_bytes deve ser positivo")


@dataclass(frozen=True)
class DashRepresentation:
    """Representação de vídeo selecionada no MPD."""

    representation_id: str
    bandwidth_bps: int
    bitrate_kbps: int
    width: int | None
    height: int | None
    frame_rate: str | None
    codecs: str | None
    mime_type: str | None
    addressing_mode: str
    segments: tuple[DashSegment, ...]


def _local_name(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children(
    element: ElementTree.Element,
    name: str,
) -> list[ElementTree.Element]:
    return [child for child in element if _local_name(child) == name]


def _first_child(
    element: ElementTree.Element,
    name: str,
) -> ElementTree.Element | None:
    return next(iter(_children(element, name)), None)


def _parse_iso_duration(value: str | None) -> float | None:
    if value is None:
        return None
    match = ISO_DURATION_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"duração ISO 8601 não suportada: {value}")
    parts = {
        key: float(raw) if raw is not None else 0.0
        for key, raw in match.groupdict().items()
    }
    duration = (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )
    if duration <= 0:
        raise ValueError(f"duração ISO 8601 deve ser positiva: {value}")
    return duration


def _positive_int(value: str | None, field: str, default: int | None = None) -> int:
    if value is None:
        if default is None:
            raise ValueError(f"{field} é obrigatório")
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{field} deve ser inteiro") from exc
    if parsed <= 0:
        raise ValueError(f"{field} deve ser positivo")
    return parsed


def _optional_int(value: str | None, field: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, field)


def _attribute(
    representation: ElementTree.Element,
    adaptation: ElementTree.Element,
    name: str,
) -> str | None:
    return representation.get(name, adaptation.get(name))


def _uri_to_local_part(value: str, field: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme or parsed.netloc:
        raise ValueError(
            f"{field} aponta para URL remota; extraia o pacote e use arquivos locais"
        )
    if parsed.query or parsed.fragment:
        raise ValueError(f"{field} com query ou fragmento não é suportado localmente")
    return unquote(parsed.path)


def _representation_base(
    mpd_path: Path,
    nodes: Sequence[ElementTree.Element],
) -> Path:
    base = mpd_path.parent
    for node in nodes:
        base_url = _first_child(node, "BaseURL")
        if base_url is None or not (base_url.text or "").strip():
            continue
        part = _uri_to_local_part(base_url.text or "", "BaseURL")
        candidate = Path(part)
        base = candidate if candidate.is_absolute() else base / candidate
    return base.resolve()


def _addressing_elements(
    nodes: Sequence[ElementTree.Element],
) -> tuple[str, list[ElementTree.Element]]:
    selected_kind: str | None = None
    selected_index = -1
    for index, node in enumerate(nodes):
        for kind in ("SegmentTemplate", "SegmentList", "SegmentBase"):
            if _first_child(node, kind) is not None and index >= selected_index:
                selected_kind = kind
                selected_index = index
    if selected_kind is None:
        raise ValueError(
            "representação sem SegmentTemplate, SegmentList ou SegmentBase"
        )

    elements = [
        child
        for node in nodes
        if (child := _first_child(node, selected_kind)) is not None
    ]
    return selected_kind, elements


def _merged_attributes(elements: Sequence[ElementTree.Element]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for element in elements:
        merged.update(element.attrib)
    return merged


def _most_specific_child(
    elements: Sequence[ElementTree.Element],
    name: str,
) -> ElementTree.Element | None:
    for element in reversed(elements):
        child = _first_child(element, name)
        if child is not None:
            return child
    return None


def _expand_timeline(
    timeline: ElementTree.Element,
    timescale: int,
    period_duration_s: float | None,
    presentation_time_offset: int,
) -> list[tuple[int, int]]:
    timeline_items = _children(timeline, "S")
    if not timeline_items:
        raise ValueError("SegmentTimeline não contém elementos S")

    expanded: list[tuple[int, int]] = []
    current_time: int | None = None
    period_end = (
        presentation_time_offset + math.ceil(period_duration_s * timescale)
        if period_duration_s is not None
        else None
    )
    for index, item in enumerate(timeline_items):
        duration = _positive_int(item.get("d"), "S@d")
        start = int(item.get("t")) if item.get("t") is not None else current_time
        if start is None:
            start = presentation_time_offset
        repeat = int(item.get("r", "0"))
        if repeat < -1:
            raise ValueError("S@r não pode ser menor que -1")

        if repeat >= 0:
            count = repeat + 1
        else:
            next_start = None
            if index + 1 < len(timeline_items):
                next_raw = timeline_items[index + 1].get("t")
                next_start = int(next_raw) if next_raw is not None else None
            boundary = next_start if next_start is not None else period_end
            if boundary is None:
                raise ValueError(
                    "S@r=-1 exige próximo S@t ou duração declarada no período/MPD"
                )
            if boundary <= start:
                raise ValueError("limite inválido para repetição S@r=-1")
            count = math.ceil((boundary - start) / duration)

        for offset in range(count):
            segment_start = start + offset * duration
            if period_end is not None and segment_start >= period_end:
                break
            segment_duration = duration
            if period_end is not None:
                segment_duration = min(segment_duration, period_end - segment_start)
            expanded.append((segment_start, segment_duration))
        current_time = start + count * duration
    return expanded


def _fixed_timeline(
    count: int,
    duration: int,
    timescale: int,
    period_duration_s: float | None,
    presentation_time_offset: int,
) -> list[tuple[int, int]]:
    values: list[tuple[int, int]] = []
    end = (
        presentation_time_offset + math.ceil(period_duration_s * timescale)
        if period_duration_s is not None
        else None
    )
    for index in range(count):
        start = presentation_time_offset + index * duration
        measured_duration = duration
        if end is not None:
            if start >= end:
                break
            measured_duration = min(duration, end - start)
        values.append((start, measured_duration))
    return values


def _render_template(
    template: str,
    representation_id: str,
    bandwidth_bps: int,
    number: int,
    time: int,
) -> str:
    values: dict[str, str | int] = {
        "RepresentationID": representation_id,
        "Bandwidth": bandwidth_bps,
        "Number": number,
        "Time": time,
    }

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if token == "$$":
            return "$"
        name = match.group(1)
        assert name is not None
        value = values[name]
        format_specifier = match.group(2)
        if format_specifier is None:
            return str(value)
        if name == "RepresentationID":
            raise ValueError("RepresentationID não aceita formatação numérica")
        return format(int(value), format_specifier[1:])

    rendered = TEMPLATE_TOKEN_PATTERN.sub(replace, template)
    if "$" in rendered:
        raise ValueError(f"token SegmentTemplate não suportado em: {template}")
    return _uri_to_local_part(rendered, "SegmentTemplate@media")


def _template_segments(
    elements: Sequence[ElementTree.Element],
    base: Path,
    representation_id: str,
    bandwidth_bps: int,
    period_duration_s: float | None,
) -> tuple[DashSegment, ...]:
    attributes = _merged_attributes(elements)
    media = attributes.get("media")
    if not media:
        raise ValueError("SegmentTemplate@media é obrigatório")
    timescale = _positive_int(attributes.get("timescale"), "timescale", 1)
    start_number = _positive_int(
        attributes.get("startNumber"),
        "startNumber",
        1,
    )
    presentation_time_offset = int(attributes.get("presentationTimeOffset", "0"))
    timeline = _most_specific_child(elements, "SegmentTimeline")
    if timeline is not None:
        timing = _expand_timeline(
            timeline,
            timescale,
            period_duration_s,
            presentation_time_offset,
        )
    else:
        duration = _positive_int(attributes.get("duration"), "duration")
        if period_duration_s is None:
            raise ValueError(
                "SegmentTemplate sem SegmentTimeline exige duração do período/MPD"
            )
        count = math.ceil(period_duration_s * timescale / duration)
        timing = _fixed_timeline(
            count,
            duration,
            timescale,
            period_duration_s,
            presentation_time_offset,
        )

    segments = []
    for index, (start, duration) in enumerate(timing):
        relative = _render_template(
            media,
            representation_id,
            bandwidth_bps,
            start_number + index,
            start,
        )
        segments.append(
            DashSegment(
                path=(base / relative).resolve(),
                duration_s=duration / timescale,
            )
        )
    return tuple(segments)


def _segment_list_segments(
    elements: Sequence[ElementTree.Element],
    base: Path,
    period_duration_s: float | None,
) -> tuple[DashSegment, ...]:
    attributes = _merged_attributes(elements)
    timescale = _positive_int(attributes.get("timescale"), "timescale", 1)
    presentation_time_offset = int(attributes.get("presentationTimeOffset", "0"))

    urls: list[ElementTree.Element] = []
    for element in reversed(elements):
        urls = _children(element, "SegmentURL")
        if urls:
            break
    if not urls:
        raise ValueError("SegmentList não contém SegmentURL")

    timeline = _most_specific_child(elements, "SegmentTimeline")
    if timeline is not None:
        timing = _expand_timeline(
            timeline,
            timescale,
            period_duration_s,
            presentation_time_offset,
        )
        if len(timing) != len(urls):
            raise ValueError(
                "quantidade de SegmentURL difere da quantidade do SegmentTimeline"
            )
    else:
        duration = _positive_int(attributes.get("duration"), "duration")
        timing = _fixed_timeline(
            len(urls),
            duration,
            timescale,
            period_duration_s,
            presentation_time_offset,
        )
        if len(timing) != len(urls):
            raise ValueError("SegmentList excede a duração declarada do período")

    segments = []
    for url, (_, duration) in zip(urls, timing):
        media = url.get("media")
        if not media:
            raise ValueError("SegmentURL@media é obrigatório")
        relative = _uri_to_local_part(media, "SegmentURL@media")
        segments.append(
            DashSegment(
                path=(base / relative).resolve(),
                duration_s=duration / timescale,
            )
        )
    return tuple(segments)


def _parse_byte_range(value: str | None, field: str) -> tuple[int, int]:
    if value is None:
        raise ValueError(f"{field} é obrigatório")
    match = re.fullmatch(r"(\d+)-(\d+)", value.strip())
    if match is None:
        raise ValueError(f"{field} deve usar o formato início-fim")
    start, end = (int(part) for part in match.groups())
    if end < start:
        raise ValueError(f"{field} termina antes de começar")
    return start, end


def _read_sidx(
    media_path: Path,
    index_start: int,
    index_end: int,
) -> tuple[DashSegment, ...]:
    """Lê um índice SIDX e converte suas referências em byte ranges."""

    if not media_path.is_file():
        raise ValueError(f"arquivo indicado por SegmentBase não encontrado: {media_path}")
    file_size = media_path.stat().st_size
    if index_end >= file_size:
        raise ValueError("SegmentBase@indexRange ultrapassa o arquivo de mídia")

    index_size = index_end - index_start + 1
    with media_path.open("rb") as handle:
        handle.seek(index_start)
        data = handle.read(index_size)
    if len(data) != index_size:
        raise ValueError("não foi possível ler todo o SegmentBase@indexRange")
    if len(data) < 8:
        raise ValueError("SegmentBase@indexRange é curto demais para uma caixa SIDX")

    box_size, box_type = struct.unpack_from(">I4s", data, 0)
    header_size = 8
    if box_size == 1:
        if len(data) < 16:
            raise ValueError("cabeçalho SIDX estendido está truncado")
        box_size = struct.unpack_from(">Q", data, 8)[0]
        header_size = 16
    if box_type != b"sidx":
        raise ValueError("SegmentBase@indexRange não aponta para uma caixa SIDX")
    if box_size != len(data):
        raise ValueError(
            "o tamanho declarado da caixa SIDX difere de SegmentBase@indexRange"
        )
    if len(data) < header_size + 4:
        raise ValueError("caixa SIDX truncada antes do cabeçalho FullBox")

    version = data[header_size]
    if version not in (0, 1):
        raise ValueError(f"versão SIDX não suportada: {version}")
    cursor = header_size + 4
    scalar_size = 4 if version == 0 else 8
    fixed_size = 8 + scalar_size * 2 + 4
    if len(data) < cursor + fixed_size:
        raise ValueError("caixa SIDX truncada antes das referências")

    _, timescale = struct.unpack_from(">II", data, cursor)
    cursor += 8
    if timescale <= 0:
        raise ValueError("timescale do SIDX deve ser positivo")
    if version == 0:
        _, first_offset = struct.unpack_from(">II", data, cursor)
    else:
        _, first_offset = struct.unpack_from(">QQ", data, cursor)
    cursor += scalar_size * 2
    _, reference_count = struct.unpack_from(">HH", data, cursor)
    cursor += 4
    expected_end = cursor + reference_count * 12
    if expected_end != len(data):
        raise ValueError("quantidade de referências do SIDX não coincide com a caixa")
    if reference_count == 0:
        raise ValueError("caixa SIDX não contém referências de mídia")

    byte_start = index_start + box_size + first_offset
    segments: list[DashSegment] = []
    for _ in range(reference_count):
        reference_info, duration, _ = struct.unpack_from(">III", data, cursor)
        cursor += 12
        reference_type = reference_info >> 31
        referenced_size = reference_info & 0x7FFFFFFF
        if reference_type:
            raise ValueError("SIDX hierárquico não é suportado nesta versão")
        if referenced_size <= 0 or duration <= 0:
            raise ValueError("referência SIDX possui tamanho ou duração inválidos")
        if byte_start + referenced_size > file_size:
            raise ValueError("referência SIDX ultrapassa o arquivo de mídia")
        segments.append(
            DashSegment(
                path=media_path,
                duration_s=duration / timescale,
                byte_start=byte_start,
                size_bytes=referenced_size,
            )
        )
        byte_start += referenced_size
    return tuple(segments)


def _segment_base_segments(
    elements: Sequence[ElementTree.Element],
    media_path: Path,
    period_duration_s: float | None,
) -> tuple[DashSegment, ...]:
    attributes = _merged_attributes(elements)
    index_start, index_end = _parse_byte_range(
        attributes.get("indexRange"),
        "SegmentBase@indexRange",
    )
    segments = _read_sidx(media_path, index_start, index_end)
    if period_duration_s is not None and not math.isclose(
        sum(item.duration_s for item in segments),
        period_duration_s,
        rel_tol=0,
        abs_tol=1e-6,
    ):
        raise ValueError("a duração total do SIDX difere da duração do período")
    return segments


def _is_video_adaptation(adaptation: ElementTree.Element) -> bool:
    content_type = (adaptation.get("contentType") or "").lower()
    mime_type = (adaptation.get("mimeType") or "").lower()
    if content_type:
        return content_type == "video"
    if mime_type:
        return mime_type.startswith("video/")
    return any(
        (representation.get("mimeType") or "").lower().startswith("video/")
        for representation in _children(adaptation, "Representation")
    )


def parse_mpd(
    mpd_path: str | Path,
    representation_ids: Sequence[str] | None = None,
    max_segments: int | None = None,
) -> tuple[DashRepresentation, ...]:
    """Resolve representações de vídeo e seus segmentos no pacote extraído."""

    source_path = Path(mpd_path).resolve()
    if not source_path.is_file():
        raise ValueError(f"MPD não encontrado: {source_path}")
    if max_segments is not None and max_segments <= 0:
        raise ValueError("max_segments deve ser positivo")

    try:
        root = ElementTree.parse(source_path).getroot()
    except ElementTree.ParseError as exc:
        raise ValueError(f"MPD XML inválido: {exc}") from exc
    if _local_name(root) != "MPD":
        raise ValueError("o documento informado não contém uma raiz MPD")
    if (root.get("type") or "static").lower() != "static":
        raise ValueError("somente MPDs estáticos podem ser importados")

    periods = _children(root, "Period")
    if not periods:
        raise ValueError("MPD não contém Period")
    video_periods = [
        period
        for period in periods
        if any(_is_video_adaptation(item) for item in _children(period, "AdaptationSet"))
    ]
    if len(video_periods) != 1:
        raise ValueError(
            "esta versão exige exatamente um Period com representações de vídeo"
        )
    period = video_periods[0]
    period_duration_s = _parse_iso_duration(period.get("duration"))
    if period_duration_s is None:
        period_duration_s = _parse_iso_duration(root.get("mediaPresentationDuration"))

    requested = tuple(representation_ids or ())
    if len(set(requested)) != len(requested):
        raise ValueError("representation_ids não pode conter duplicatas")
    requested_set = set(requested)
    representations: list[DashRepresentation] = []
    seen_ids: set[str] = set()

    for adaptation in _children(period, "AdaptationSet"):
        if not _is_video_adaptation(adaptation):
            continue
        for index, representation in enumerate(
            _children(adaptation, "Representation"),
            start=1,
        ):
            representation_id = representation.get("id") or f"representation-{index}"
            if representation_id in seen_ids:
                raise ValueError(f"Representation@id duplicado: {representation_id}")
            seen_ids.add(representation_id)
            if requested_set and representation_id not in requested_set:
                continue

            bandwidth_bps = _positive_int(
                representation.get("bandwidth"),
                f"Representation {representation_id} bandwidth",
            )
            bitrate_kbps = (bandwidth_bps + 500) // 1000
            codecs = _attribute(representation, adaptation, "codecs")
            if codecs and not any(
                item.strip().lower().startswith(("vvc1", "vvi1"))
                for item in codecs.split(",")
            ):
                raise ValueError(
                    f"representação {representation_id} não declara codec VVC: {codecs}"
                )

            nodes = (period, adaptation, representation)
            base = _representation_base(source_path, (root, *nodes))
            kind, addressing = _addressing_elements(nodes)
            if kind == "SegmentTemplate":
                segments = _template_segments(
                    addressing,
                    base,
                    representation_id,
                    bandwidth_bps,
                    period_duration_s,
                )
            elif kind == "SegmentList":
                segments = _segment_list_segments(
                    addressing,
                    base,
                    period_duration_s,
                )
            else:
                segments = _segment_base_segments(
                    addressing,
                    base,
                    period_duration_s,
                )
            if max_segments is not None:
                segments = segments[:max_segments]
            if not segments:
                raise ValueError(f"representação {representation_id} não possui segmentos")

            representations.append(
                DashRepresentation(
                    representation_id=representation_id,
                    bandwidth_bps=bandwidth_bps,
                    bitrate_kbps=bitrate_kbps,
                    width=_optional_int(
                        _attribute(representation, adaptation, "width"),
                        "width",
                    ),
                    height=_optional_int(
                        _attribute(representation, adaptation, "height"),
                        "height",
                    ),
                    frame_rate=_attribute(representation, adaptation, "frameRate"),
                    codecs=codecs,
                    mime_type=_attribute(representation, adaptation, "mimeType"),
                    addressing_mode=kind,
                    segments=segments,
                )
            )

    missing = requested_set - {item.representation_id for item in representations}
    if missing:
        raise ValueError(
            "representações solicitadas não encontradas: " + ", ".join(sorted(missing))
        )
    if not representations:
        raise ValueError("nenhuma representação de vídeo foi selecionada")

    bitrate_to_id: dict[int, str] = {}
    for representation in representations:
        other = bitrate_to_id.get(representation.bitrate_kbps)
        if other is not None:
            raise ValueError(
                "duas representações resultam no mesmo bitrate_kbps após "
                f"arredondamento: {other} e {representation.representation_id}"
            )
        bitrate_to_id[representation.bitrate_kbps] = representation.representation_id

    segment_counts = {len(item.segments) for item in representations}
    if len(segment_counts) != 1:
        raise ValueError("as representações possuem quantidades diferentes de segmentos")
    for segment_index in range(next(iter(segment_counts))):
        durations = [item.segments[segment_index].duration_s for item in representations]
        if not all(
            math.isclose(value, durations[0], rel_tol=0, abs_tol=1e-9)
            for value in durations[1:]
        ):
            raise ValueError(
                f"as representações têm durações diferentes no segmento {segment_index}"
            )
    return tuple(sorted(representations, key=lambda item: item.bitrate_kbps))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _segment_size(segment: DashSegment) -> int:
    return (
        segment.size_bytes
        if segment.size_bytes is not None
        else segment.path.stat().st_size
    )


def _sha256_segment(segment: DashSegment) -> str:
    if segment.byte_start is None:
        return _sha256(segment.path)

    digest = hashlib.sha256()
    remaining = _segment_size(segment)
    with segment.path.open("rb") as handle:
        handle.seek(segment.byte_start)
        while remaining:
            chunk = handle.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError("o byte range terminou antes do tamanho declarado")
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def _logical_path(path: Path, package_root: Path) -> str:
    try:
        return path.relative_to(package_root).as_posix()
    except ValueError:
        return str(path)


def _logical_segment_source(segment: DashSegment, package_root: Path) -> str:
    source = _logical_path(segment.path, package_root)
    if segment.byte_start is None:
        return source
    byte_end = segment.byte_start + _segment_size(segment) - 1
    return f"{source}#bytes={segment.byte_start}-{byte_end}"


def _ensure_available(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"arquivo já existe: {path}; use --overwrite para substituí-lo"
        )


def write_protocol_config(
    template_path: str | Path,
    output_path: str | Path,
    manifest: SegmentManifest,
    manifest_path: str | Path,
    bandwidth_scale: float = 1.0,
    overwrite: bool = False,
) -> Path:
    """Copia um protocolo e injeta a escada e o manifesto importados."""

    source = Path(template_path).resolve()
    target = Path(output_path).resolve()
    if not source.is_file():
        raise ValueError(f"template de protocolo não encontrado: {source}")
    _ensure_available(target, overwrite)
    with source.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw.get("experiment_config"), dict):
        raise ValueError("template não contém experiment_config")
    if not math.isfinite(bandwidth_scale) or bandwidth_scale <= 0:
        raise ValueError("bandwidth_scale deve ser positivo e finito")

    relative_manifest = os.path.relpath(Path(manifest_path).resolve(), target.parent)
    raw["segment_manifest"] = Path(relative_manifest).as_posix()
    raw["experiment_config"]["bitrates_kbps"] = list(manifest.bitrates_kbps)
    raw["experiment_config"]["segment_duration_s"] = manifest.get(
        0,
        manifest.bitrates_kbps[0],
    ).duration_s
    if not math.isclose(bandwidth_scale, 1.0):
        for field in ("training_traces", "evaluation_traces"):
            raw[field] = [
                {
                    "path": item if isinstance(item, str) else item["path"],
                    "bandwidth_scale": bandwidth_scale,
                }
                for item in raw.get(field, [])
            ]
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(raw, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return target


def import_dvb_dash(
    mpd_path: str | Path,
    manifest_path: str | Path,
    *,
    package_name: str | None = None,
    sequence: str | None = None,
    source_url: str = DVB_VVC_SOURCE_URL,
    attribution: str,
    license_name: str | None = None,
    license_url: str | None = None,
    archive_path: str | Path | None = None,
    representation_ids: Sequence[str] | None = None,
    max_segments: int | None = None,
    provenance_path: str | Path | None = None,
    protocol_template_path: str | Path | None = None,
    protocol_config_path: str | Path | None = None,
    bandwidth_scale: float = 1.0,
    overwrite: bool = False,
) -> dict[str, object]:
    """Gera manifesto, proveniência e, opcionalmente, protocolo experimental."""

    mpd = Path(mpd_path).resolve()
    output = Path(manifest_path).resolve()
    provenance = (
        Path(provenance_path).resolve()
        if provenance_path is not None
        else output.with_suffix(".provenance.json")
    )
    protocol_output = (
        Path(protocol_config_path).resolve()
        if protocol_config_path is not None
        else None
    )
    if bool(protocol_template_path) != bool(protocol_output):
        raise ValueError(
            "protocol_template_path e protocol_config_path devem ser usados juntos"
        )
    if not attribution.strip():
        raise ValueError("attribution não pode ser vazia")
    if not source_url.strip():
        raise ValueError("source_url não pode ser vazia")

    archive = Path(archive_path).resolve() if archive_path is not None else None
    if archive is not None and not archive.is_file():
        raise ValueError(f"arquivo original não encontrado: {archive}")
    _ensure_available(output, overwrite)
    _ensure_available(provenance, overwrite)
    if protocol_output is not None:
        _ensure_available(protocol_output, overwrite)

    representations = parse_mpd(mpd, representation_ids, max_segments)
    for representation in representations:
        for segment in representation.segments:
            if not segment.path.is_file():
                raise ValueError(
                    "segmento referenciado pelo MPD não foi encontrado: "
                    f"{segment.path}"
                )
            if _segment_size(segment) <= 0:
                raise ValueError(f"segmento vazio: {segment.path}")
            if (
                segment.byte_start is not None
                and segment.byte_start + _segment_size(segment)
                > segment.path.stat().st_size
            ):
                raise ValueError(f"byte range inválido: {segment.path}")

    chosen_package_name = (package_name or mpd.parent.name).strip()
    chosen_sequence = (sequence or chosen_package_name or mpd.stem).strip()
    if not chosen_sequence:
        raise ValueError("sequence não pode ser vazia")

    output.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for representation in representations:
        for segment_index, segment in enumerate(representation.segments):
            rows.append(
                {
                    "sequence": chosen_sequence,
                    "segment": segment_index,
                    "bitrate_kbps": representation.bitrate_kbps,
                    "duration_s": f"{segment.duration_s:.9f}".rstrip("0").rstrip("."),
                    "size_bytes": _segment_size(segment),
                    "psnr_y_db": "",
                    "source_file": _logical_segment_source(segment, mpd.parent),
                    "sha256": _sha256_segment(segment),
                }
            )
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    manifest = load_segment_manifest(output)

    generated_protocol: Path | None = None
    if protocol_output is not None and protocol_template_path is not None:
        generated_protocol = write_protocol_config(
            protocol_template_path,
            protocol_output,
            manifest,
            output,
            bandwidth_scale=bandwidth_scale,
            overwrite=overwrite,
        )

    representation_metadata = []
    for representation in representations:
        total_bytes = sum(_segment_size(item) for item in representation.segments)
        total_duration = sum(item.duration_s for item in representation.segments)
        representation_metadata.append(
            {
                "id": representation.representation_id,
                "bandwidth_bps": representation.bandwidth_bps,
                "bitrate_kbps": representation.bitrate_kbps,
                "width": representation.width,
                "height": representation.height,
                "frame_rate": representation.frame_rate,
                "codecs": representation.codecs,
                "mime_type": representation.mime_type,
                "addressing_mode": representation.addressing_mode,
                "segment_count": len(representation.segments),
                "total_media_bytes": total_bytes,
                "average_payload_bitrate_kbps": (
                    total_bytes * 8 / 1000 / total_duration
                ),
            }
        )

    provenance_document: dict[str, object] = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "importer": {
            "name": "dvb_dash_importer.py",
            "sha256": _sha256(Path(__file__).resolve()),
        },
        "package": {
            "name": chosen_package_name,
            "source_url": source_url.strip(),
            "archive": (
                {
                    "file": archive.name,
                    "size_bytes": archive.stat().st_size,
                    "sha256": _sha256(archive),
                }
                if archive is not None
                else None
            ),
            "mpd": {
                "file": _logical_path(mpd, mpd.parent),
                "size_bytes": mpd.stat().st_size,
                "sha256": _sha256(mpd),
            },
        },
        "rights": {
            "attribution": attribution.strip(),
            "license_name": license_name.strip() if license_name else None,
            "license_url": license_url.strip() if license_url else None,
            "note": "Verificar os termos específicos do pacote na página da DVB.",
        },
        "selection": {
            "requested_representation_ids": list(representation_ids or ()),
            "max_segments": max_segments,
            "bandwidth_scale": bandwidth_scale,
            "adaptive_ladder": len(representations) >= 2,
        },
        "representations": representation_metadata,
        "quality": {
            "psnr_y_db": None,
            "reason": (
                "o pacote não inclui o master YUV de referência exato; "
                "nenhum valor de PSNR foi inferido"
            ),
        },
        "manifest": {
            **manifest.metadata(),
            "file": output.name,
            "sha256": _sha256(output),
        },
        "protocol_config": (
            {
                "file": generated_protocol.name,
                "sha256": _sha256(generated_protocol),
            }
            if generated_protocol is not None
            else None
        ),
    }
    provenance.parent.mkdir(parents=True, exist_ok=True)
    with provenance.open("w", encoding="utf-8") as handle:
        json.dump(provenance_document, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    return {
        "manifest": str(output),
        "provenance": str(provenance),
        "protocol_config": str(generated_protocol) if generated_protocol else None,
        "sequence": manifest.sequence,
        "segment_count": manifest.segment_count,
        "bitrates_kbps": list(manifest.bitrates_kbps),
        "adaptive_ladder": len(manifest.bitrates_kbps) >= 2,
    }
