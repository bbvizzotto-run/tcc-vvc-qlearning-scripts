"""Canonicalização auditável de escadas VVC por taxa média medida."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Sequence

from segment_manifest import load_segment_manifest


CANONICALIZATION_SCHEMA_VERSION = 2
LOSSLESS_PSNR_CAP_DB = Decimal("100")
CANONICAL_FIELDS = (
    "sequence",
    "segment",
    "representation_id",
    "encoder_target_kbps",
    "bitrate_kbps",
    "duration_s",
    "size_bytes",
    "psnr_y_db",
    "source_file",
    "sha256",
)


@dataclass(frozen=True)
class RepresentationMapping:
    representation_id: str
    encoder_target_kbps: int
    operational_bitrate_kbps: int
    measured_bitrate_kbps: Decimal
    total_size_bytes: int
    total_duration_s: Decimal
    min_segment_bitrate_kbps: Decimal
    max_segment_bitrate_kbps: Decimal
    mean_psnr_y_db: Decimal

    def to_dict(self) -> dict[str, object]:
        return {
            "representation_id": self.representation_id,
            "encoder_target_kbps": self.encoder_target_kbps,
            "operational_bitrate_kbps": self.operational_bitrate_kbps,
            "measured_bitrate_kbps": _decimal_text(
                self.measured_bitrate_kbps,
                places=6,
            ),
            "total_size_bytes": self.total_size_bytes,
            "total_duration_s": _decimal_text(self.total_duration_s),
            "min_segment_bitrate_kbps": _decimal_text(
                self.min_segment_bitrate_kbps,
                places=6,
            ),
            "max_segment_bitrate_kbps": _decimal_text(
                self.max_segment_bitrate_kbps,
                places=6,
            ),
            "mean_psnr_y_db": _decimal_text(self.mean_psnr_y_db, places=6),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decimal_text(value: Decimal, places: int | None = None) -> str:
    if places is not None:
        quantum = Decimal(1).scaleb(-places)
        value = value.quantize(quantum)
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _load_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or ())
        rows = [dict(row) for row in reader]
    return fields, rows


def _validate_complete_metrics(rows: Sequence[dict[str, str]]) -> None:
    for index, row in enumerate(rows, start=2):
        for field in ("psnr_y_db", "sha256"):
            if not (row.get(field) or "").strip():
                raise ValueError(
                    f"o manifesto bruto exige {field} preenchido na linha {index}"
                )


def _validate_monotonicity(rows: Sequence[dict[str, str]]) -> int:
    lossless_psnr_ties = 0
    by_segment: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_segment[int(row["segment"])].append(row)
    for segment, segment_rows in by_segment.items():
        ordered = sorted(segment_rows, key=lambda row: int(row["bitrate_kbps"]))
        for previous, current in zip(ordered, ordered[1:]):
            if int(current["size_bytes"]) <= int(previous["size_bytes"]):
                raise ValueError(
                    "size_bytes não é estritamente crescente no segmento "
                    f"{segment}: {previous['bitrate_kbps']} -> "
                    f"{current['bitrate_kbps']} kbps"
                )
            previous_psnr = Decimal(previous["psnr_y_db"])
            current_psnr = Decimal(current["psnr_y_db"])
            if current_psnr < previous_psnr or (
                current_psnr == previous_psnr
                and current_psnr != LOSSLESS_PSNR_CAP_DB
            ):
                raise ValueError(
                    "psnr_y_db não segue a política de monotonicidade no segmento "
                    f"{segment}: {previous['bitrate_kbps']} -> "
                    f"{current['bitrate_kbps']} kbps"
                )
            if current_psnr == previous_psnr == LOSSLESS_PSNR_CAP_DB:
                lossless_psnr_ties += 1
    return lossless_psnr_ties


def _representation_mappings(
    rows: Sequence[dict[str, str]],
) -> tuple[RepresentationMapping, ...]:
    by_target: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_target[int(row["bitrate_kbps"])].append(row)

    mappings = []
    for level, target in enumerate(sorted(by_target)):
        target_rows = by_target[target]
        total_bytes = sum(int(row["size_bytes"]) for row in target_rows)
        total_duration = sum(
            (Decimal(row["duration_s"]) for row in target_rows),
            start=Decimal(0),
        )
        measured = Decimal(total_bytes * 8) / (total_duration * Decimal(1000))
        operational = int(measured.to_integral_value(rounding=ROUND_HALF_UP))
        segment_rates = [
            Decimal(int(row["size_bytes"]) * 8)
            / (Decimal(row["duration_s"]) * Decimal(1000))
            for row in target_rows
        ]
        mean_psnr = sum(
            (Decimal(row["psnr_y_db"]) for row in target_rows),
            start=Decimal(0),
        ) / Decimal(len(target_rows))
        mappings.append(
            RepresentationMapping(
                representation_id=f"L{level}",
                encoder_target_kbps=target,
                operational_bitrate_kbps=operational,
                measured_bitrate_kbps=measured,
                total_size_bytes=total_bytes,
                total_duration_s=total_duration,
                min_segment_bitrate_kbps=min(segment_rates),
                max_segment_bitrate_kbps=max(segment_rates),
                mean_psnr_y_db=mean_psnr,
            )
        )

    operational_ladder = tuple(
        mapping.operational_bitrate_kbps for mapping in mappings
    )
    if tuple(sorted(set(operational_ladder))) != operational_ladder:
        raise ValueError(
            "o arredondamento da taxa média não produz uma escada estritamente crescente"
        )
    return tuple(mappings)


def _audit_source_provenance(
    raw: dict[str, object],
    rows: Sequence[dict[str, str]],
    targets: Sequence[int],
    source_manifest_sha256: str,
    source_sequence: str,
) -> dict[str, object]:
    configuration = raw.get("configuration")
    if not isinstance(configuration, dict):
        raise ValueError("proveniência sem configuration")
    configured_targets = [
        int(value) for value in configuration.get("bitrates_kbps", [])
    ]
    if configured_targets != list(targets):
        raise ValueError("escada da proveniência difere do manifesto bruto")

    source_config = configuration.get("source")
    if not isinstance(source_config, dict):
        raise ValueError("proveniência sem configuration.source")
    segment_count = len({int(row["segment"]) for row in rows})
    if int(source_config.get("segment_count", -1)) != segment_count:
        raise ValueError("quantidade de segmentos difere da proveniência")

    manifest = raw.get("manifest")
    if not isinstance(manifest, dict):
        raise ValueError("proveniência sem resumo do manifesto")
    if manifest.get("manifest_sha256") != source_manifest_sha256:
        raise ValueError("hash do manifesto bruto difere da proveniência")
    if manifest.get("sequence") != source_sequence:
        raise ValueError("sequência do manifesto difere da proveniência")
    if int(manifest.get("segment_count", -1)) != segment_count:
        raise ValueError("resumo do manifesto tem quantidade de segmentos inválida")
    if [int(value) for value in manifest.get("bitrates_kbps", [])] != list(
        targets
    ):
        raise ValueError("resumo do manifesto tem escada inválida")

    commands = raw.get("commands")
    if not isinstance(commands, list) or len(commands) != len(rows):
        raise ValueError("quantidade de comandos difere do manifesto bruto")
    expected_keys = {
        (int(row["segment"]), int(row["bitrate_kbps"])) for row in rows
    }
    command_keys: set[tuple[int, int]] = set()
    require_poc0idr = (
        configuration.get("encoder", {}).get("refresh_type") == "idr_no_radl"
        if isinstance(configuration.get("encoder"), dict)
        else False
    )
    for command in commands:
        if not isinstance(command, dict):
            raise ValueError("entrada inválida em commands")
        key = (int(command["segment"]), int(command["bitrate_kbps"]))
        if key in command_keys:
            raise ValueError("comando duplicado na proveniência")
        command_keys.add(key)
        encoder = command.get("encoder")
        if not isinstance(encoder, list):
            raise ValueError("comando de encoder ausente na proveniência")
        if require_poc0idr:
            try:
                value = encoder[encoder.index("--additional") + 1]
            except (ValueError, IndexError) as exc:
                raise ValueError("comando sem POC0IDR explícito") from exc
            if value != "POC0IDR=1":
                raise ValueError("comando sem POC0IDR=1")
    if command_keys != expected_keys:
        raise ValueError("comandos não cobrem a matriz completa do manifesto")

    return {
        "pipeline_schema_version": raw.get("pipeline_schema_version"),
        "generated_at_utc": raw.get("generated_at_utc"),
        "pipeline": raw.get("pipeline"),
        "source": raw.get("source"),
        "tools": raw.get("tools"),
        "runtime": raw.get("runtime"),
        "configuration_sha256": raw.get("configuration_sha256"),
        "source_manifest_sha256_validated": source_manifest_sha256,
        "commands_validated": len(commands),
        "poc0idr_validated": require_poc0idr,
    }


def _audit_source_preparation(
    provenance_path: Path,
    vvc_source: object,
    vvc_configuration: object | None = None,
) -> dict[str, object]:
    raw = json.loads(provenance_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("a proveniência da preparação deve ser um objeto JSON")
    if not isinstance(vvc_source, dict):
        raise ValueError("proveniência VVC sem resumo da fonte")

    if isinstance(raw.get("source_sequence"), dict):
        return _audit_png_source_preparation(
            provenance_path,
            raw,
            vvc_source,
            vvc_configuration,
        )

    archive = raw.get("source_archive")
    clip = raw.get("clip")
    configuration = raw.get("configuration")
    if not isinstance(archive, dict):
        raise ValueError("proveniência da preparação sem source_archive")
    if not isinstance(clip, dict):
        raise ValueError("proveniência da preparação sem clip")
    if not isinstance(configuration, dict):
        raise ValueError("proveniência da preparação sem configuration")
    configured_source = configuration.get("source")
    configured_clip = configuration.get("clip")
    if not isinstance(configured_source, dict) or not isinstance(
        configured_clip,
        dict,
    ):
        raise ValueError("configuração da preparação incompleta")

    if archive.get("sha256") != configured_source.get("expected_sha256"):
        raise ValueError("hash do XZ difere da configuração da preparação")
    if archive.get("url") != configured_source.get("url"):
        raise ValueError("URL do XZ difere da configuração da preparação")
    if clip.get("sha256") != vvc_source.get("sha256"):
        raise ValueError("hash do YUV preparado difere da fonte do pipeline VVC")
    if int(clip.get("size_bytes", -1)) != int(
        vvc_source.get("size_bytes", -2)
    ):
        raise ValueError("tamanho do YUV preparado difere da fonte do pipeline VVC")
    if int(clip.get("frame_count", -1)) != int(
        vvc_source.get("available_frames", -2)
    ):
        raise ValueError("quadros do YUV preparado diferem da fonte do pipeline VVC")

    for field in ("start_frame", "frame_count", "pixel_format"):
        if clip.get(field) != configured_clip.get(field):
            raise ValueError(
                f"{field} do trecho difere da configuração da preparação"
            )

    return {
        "provenance_file": provenance_path.name,
        "provenance_sha256": _sha256(provenance_path),
        "source_preparation_schema_version": raw.get(
            "source_preparation_schema_version"
        ),
        "generated_at_utc": raw.get("generated_at_utc"),
        "configuration_sha256": raw.get("configuration_sha256"),
        "source_archive": archive,
        "clip": clip,
        "ffmpeg": raw.get("ffmpeg"),
        "pipeline": raw.get("pipeline"),
        "runtime": raw.get("runtime"),
    }


def _audit_png_source_preparation(
    provenance_path: Path,
    raw: dict[str, object],
    vvc_source: dict[str, object],
    vvc_configuration: object,
) -> dict[str, object]:
    """Audita a sequência PNG fixada e sua transformação para YUV."""

    sequence = raw.get("source_sequence")
    clip = raw.get("clip")
    normalization = raw.get("normalization")
    configuration = raw.get("configuration")
    if not isinstance(sequence, dict):
        raise ValueError("proveniência PNG sem source_sequence")
    if not isinstance(clip, dict):
        raise ValueError("proveniência PNG sem clip")
    if not isinstance(normalization, dict):
        raise ValueError("proveniência PNG sem normalization")
    if not isinstance(configuration, dict):
        raise ValueError("proveniência PNG sem configuration")

    configured_source = configuration.get("source")
    configured_clip = configuration.get("clip")
    if not isinstance(configured_source, dict) or not isinstance(
        configured_clip,
        dict,
    ):
        raise ValueError("configuração da preparação PNG incompleta")

    expected_sequence_sha256 = configured_source.get(
        "expected_sequence_sha256"
    )
    if not expected_sequence_sha256:
        raise ValueError("sequência PNG não possui SHA-256 esperado fixado")
    if sequence.get("sequence_sha256") != expected_sequence_sha256:
        raise ValueError("hash da sequência PNG difere da configuração")
    if sequence.get("expected_sequence_sha256") != expected_sequence_sha256:
        raise ValueError("hash esperado da sequência PNG é inconsistente")
    if sequence.get("integrity_pinned") is not True:
        raise ValueError("integridade da sequência PNG não está fixada")

    source_fields = (
        "name",
        "base_url",
        "index_url",
        "license_name",
        "license_url",
        "first_frame",
        "frame_count",
        "width",
        "height",
        "fps_num",
        "fps_den",
    )
    for field in source_fields:
        if sequence.get(field) != configured_source.get(field):
            raise ValueError(
                f"{field} da sequência PNG difere da configuração"
            )

    first_frame = int(configured_source["first_frame"])
    frame_count = int(configured_source["frame_count"])
    if int(sequence.get("last_frame", -1)) != first_frame + frame_count - 1:
        raise ValueError("último quadro da sequência PNG é inconsistente")
    if int(sequence.get("downloaded_frames", -1)) + int(
        sequence.get("reused_frames", -1)
    ) != frame_count:
        raise ValueError("cobertura de download/cache da sequência PNG é inválida")

    frames = sequence.get("frames")
    if not isinstance(frames, list) or len(frames) != frame_count:
        raise ValueError("registros por quadro da sequência PNG estão incompletos")
    filename_pattern = str(configured_source.get("filename_pattern", ""))
    aggregate = hashlib.sha256()
    total_size_bytes = 0
    for offset, record in enumerate(frames):
        if not isinstance(record, dict):
            raise ValueError("registro de quadro PNG inválido")
        frame_number = first_frame + offset
        try:
            expected_filename = filename_pattern % frame_number
        except (TypeError, ValueError) as exc:
            raise ValueError("padrão de nome PNG inválido") from exc
        if int(record.get("frame_number", -1)) != frame_number:
            raise ValueError("ordem dos quadros PNG é inválida")
        if record.get("filename") != expected_filename:
            raise ValueError("nome de quadro PNG difere da configuração")
        size_bytes = int(record.get("size_bytes", 0))
        frame_sha256 = str(record.get("sha256", ""))
        if size_bytes <= 0:
            raise ValueError("quadro PNG possui tamanho inválido")
        if len(frame_sha256) != 64:
            raise ValueError("quadro PNG possui SHA-256 inválido")
        try:
            int(frame_sha256, 16)
        except ValueError as exc:
            raise ValueError("quadro PNG possui SHA-256 inválido") from exc

        png = record.get("png")
        if not isinstance(png, dict):
            raise ValueError("registro PNG sem metadados IHDR")
        expected_header = {
            "width": int(configured_source["width"]),
            "height": int(configured_source["height"]),
            "bit_depth": int(configured_source["bit_depth"]),
            "compression_method": 0,
            "filter_method": 0,
        }
        if any(png.get(field) != value for field, value in expected_header.items()):
            raise ValueError("metadados IHDR da sequência PNG são inválidos")

        total_size_bytes += size_bytes
        aggregate.update(
            f"{expected_filename}\t{size_bytes}\t{frame_sha256}\n".encode(
                "ascii"
            )
        )

    if total_size_bytes != int(sequence.get("total_size_bytes", -1)):
        raise ValueError("tamanho agregado da sequência PNG é inconsistente")
    if aggregate.hexdigest() != expected_sequence_sha256:
        raise ValueError("SHA-256 agregado dos registros PNG é inconsistente")

    if clip.get("sha256") != vvc_source.get("sha256"):
        raise ValueError("hash do YUV preparado difere da fonte do pipeline VVC")
    if int(clip.get("size_bytes", -1)) != int(
        vvc_source.get("size_bytes", -2)
    ):
        raise ValueError("tamanho do YUV preparado difere da fonte do pipeline VVC")
    if int(clip.get("frame_count", -1)) != int(
        vvc_source.get("available_frames", -2)
    ):
        raise ValueError("quadros do YUV preparado diferem da fonte do pipeline VVC")

    for field in ("width", "height", "pixel_format"):
        if clip.get(field) != configured_clip.get(field):
            raise ValueError(
                f"{field} do trecho PNG difere da configuração"
            )
    if int(clip.get("frame_count", -1)) != frame_count:
        raise ValueError("quantidade de quadros do trecho PNG é inválida")

    active_region = normalization.get("active_region")
    expected_region = {
        "x": int(configured_clip["pad_x"]),
        "y": int(configured_clip["pad_y"]),
        "width": int(configured_source["width"]),
        "height": int(configured_source["height"]),
    }
    if normalization.get("policy") != "symmetric_letterbox":
        raise ValueError("política de normalização PNG inválida")
    if active_region != expected_region:
        raise ValueError("região ativa da normalização PNG é inválida")
    if not isinstance(vvc_configuration, dict):
        raise ValueError("configuração VVC ausente na auditoria da fonte PNG")
    decoder = vvc_configuration.get("decoder")
    if not isinstance(decoder, dict):
        raise ValueError("configuração VVC sem decoder")
    if decoder.get("quality_region") != active_region:
        raise ValueError(
            "região de qualidade VVC difere da área ativa da fonte PNG"
        )

    sequence_summary = {
        key: value for key, value in sequence.items() if key != "frames"
    }
    return {
        "provenance_file": provenance_path.name,
        "provenance_sha256": _sha256(provenance_path),
        "source_preparation_schema_version": raw.get(
            "preparation_schema_version"
        ),
        "generated_at_utc": raw.get("generated_at_utc"),
        "configuration_sha256": raw.get("configuration_sha256"),
        "source_sequence": sequence_summary,
        "frame_records_validated": len(frames),
        "quality_region_validated": True,
        "normalization": normalization,
        "clip": clip,
        "pipeline": raw.get("pipeline"),
        "runtime": raw.get("runtime"),
    }


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CANONICAL_FIELDS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def canonicalize_manifest(
    source_manifest: str | Path,
    source_provenance: str | Path,
    output_manifest: str | Path,
    output_provenance: str | Path | None = None,
    *,
    source_preparation_provenance: str | Path | None = None,
    overwrite: bool = False,
) -> dict[str, object]:
    """Converte alvos de encoder em rótulos de taxa média medida."""

    source_path = Path(source_manifest).resolve()
    provenance_path = Path(source_provenance).resolve()
    preparation_path = (
        Path(source_preparation_provenance).resolve()
        if source_preparation_provenance is not None
        else None
    )
    output_path = Path(output_manifest).resolve()
    canonical_provenance_path = (
        Path(output_provenance).resolve()
        if output_provenance is not None
        else output_path.with_suffix(".provenance.json")
    )
    input_paths = {source_path, provenance_path}
    if preparation_path is not None:
        input_paths.add(preparation_path)
    if output_path in input_paths:
        raise ValueError("as entradas não podem ser substituídas")
    if canonical_provenance_path in input_paths | {output_path}:
        raise ValueError("a proveniência de saída deve usar um arquivo distinto")
    if output_path.suffix.lower() != ".csv":
        raise ValueError("output_manifest deve usar a extensão .csv")
    if not overwrite:
        for path in (output_path, canonical_provenance_path):
            if path.exists():
                raise FileExistsError(
                    f"arquivo já existe: {path}; use --overwrite conscientemente"
                )

    raw_manifest = load_segment_manifest(source_path)
    _, rows = _load_rows(source_path)
    _validate_complete_metrics(rows)
    lossless_psnr_ties = _validate_monotonicity(rows)
    mappings = _representation_mappings(rows)
    targets = tuple(mapping.encoder_target_kbps for mapping in mappings)
    raw_provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if not isinstance(raw_provenance, dict):
        raise ValueError("a proveniência deve ser um objeto JSON")
    source_audit = _audit_source_provenance(
        raw_provenance,
        rows,
        targets,
        raw_manifest.manifest_sha256 or "",
        raw_manifest.sequence,
    )
    preparation_audit = (
        _audit_source_preparation(
            preparation_path,
            raw_provenance.get("source"),
            raw_provenance.get("configuration"),
        )
        if preparation_path is not None
        else None
    )

    by_target = {mapping.encoder_target_kbps: mapping for mapping in mappings}
    canonical_rows: list[dict[str, object]] = []
    for row in rows:
        target = int(row["bitrate_kbps"])
        mapping = by_target[target]
        canonical_rows.append(
            {
                "sequence": row["sequence"],
                "segment": int(row["segment"]),
                "representation_id": mapping.representation_id,
                "encoder_target_kbps": target,
                "bitrate_kbps": mapping.operational_bitrate_kbps,
                "duration_s": row["duration_s"],
                "size_bytes": int(row["size_bytes"]),
                "psnr_y_db": row["psnr_y_db"],
                "source_file": row.get("source_file", ""),
                "sha256": row.get("sha256", ""),
            }
        )
    canonical_rows.sort(
        key=lambda row: (int(row["segment"]), int(row["bitrate_kbps"]))
    )
    _write_csv(output_path, canonical_rows)
    canonical_manifest = load_segment_manifest(output_path)
    output_hash = _sha256(output_path)

    canonical_provenance: dict[str, object] = {
        "canonicalization_schema_version": CANONICALIZATION_SCHEMA_VERSION,
        "algorithm": {
            "name": "aggregate_payload_bitrate_round_half_up",
            "formula": "sum(size_bytes) * 8 / sum(duration_s) / 1000",
            "rounding": "nearest integer kbps, ROUND_HALF_UP",
            "purpose": (
                "separate the VVenC encoder target from the operational "
                "representation bitrate used by ABR controllers"
            ),
        },
        "input": {
            "manifest_file": source_path.name,
            "manifest_sha256": _sha256(source_path),
            "provenance_file": provenance_path.name,
            "provenance_sha256": _sha256(provenance_path),
            **(
                {
                    "source_preparation_provenance_file": preparation_path.name,
                    "source_preparation_provenance_sha256": _sha256(
                        preparation_path
                    ),
                }
                if preparation_path is not None
                else {}
            ),
        },
        "output": {
            "manifest_file": output_path.name,
            "manifest_sha256": output_hash,
            "row_count": len(canonical_rows),
            "segment_count": canonical_manifest.segment_count,
            "operational_bitrates_kbps": list(
                canonical_manifest.bitrates_kbps
            ),
        },
        "representations": [mapping.to_dict() for mapping in mappings],
        "source_execution_audit": source_audit,
        **(
            {"source_preparation_audit": preparation_audit}
            if preparation_audit is not None
            else {}
        ),
        "validation": {
            "complete_ladder": True,
            "complete_psnr_y": True,
            "complete_sha256": True,
            "strictly_increasing_size_per_segment": True,
            "psnr_y_monotonicity_policy": (
                "strictly increasing except equal values at the "
                "100 dB lossless cap"
            ),
            "lossless_psnr_cap_db": _decimal_text(LOSSLESS_PSNR_CAP_DB),
            "lossless_psnr_ties": lossless_psnr_ties,
            "source_sequence": raw_manifest.sequence,
        },
    }
    _write_json(canonical_provenance_path, canonical_provenance)
    return canonical_provenance
