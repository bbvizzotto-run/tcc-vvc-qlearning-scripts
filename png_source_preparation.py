"""Aquisição e normalização reproduzível de uma sequência pública de PNGs."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence
from urllib.parse import urljoin


SCHEMA_VERSION = 1
SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")
FRAME_PATTERN = re.compile(r"[^%]*%0?\d*d[^%]*")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
FrameDownloader = Callable[[str, Path, float, int], None]
ProgressReporter = Callable[[str], None]


@dataclass(frozen=True)
class PngSequenceConfig:
    name: str
    base_url: str
    index_url: str
    license_name: str
    license_url: str
    cache_dir: Path
    filename_pattern: str
    first_frame: int
    frame_count: int
    width: int
    height: int
    fps_num: int
    fps_den: int
    bit_depth: int = 8
    expected_sequence_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("source.name não pode ser vazio")
        if not self.base_url.strip() or not self.index_url.strip():
            raise ValueError("source.base_url e source.index_url são obrigatórias")
        if not self.license_name.strip() or not self.license_url.strip():
            raise ValueError("a licença da fonte deve ser informada")
        if FRAME_PATTERN.fullmatch(self.filename_pattern) is None:
            raise ValueError(
                "source.filename_pattern deve conter um único marcador inteiro, "
                "por exemplo %05d.png"
            )
        try:
            first_name = self.filename_pattern % self.first_frame
            last_name = self.filename_pattern % self.last_frame
        except (TypeError, ValueError) as exc:
            raise ValueError("source.filename_pattern é inválido") from exc
        if first_name == last_name and self.frame_count > 1:
            raise ValueError("source.filename_pattern não distingue os quadros")
        if Path(first_name).name != first_name or Path(last_name).name != last_name:
            raise ValueError("source.filename_pattern deve produzir apenas o nome")
        if self.first_frame < 0:
            raise ValueError("source.first_frame não pode ser negativo")
        if self.frame_count <= 0:
            raise ValueError("source.frame_count deve ser positivo")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("source.width e source.height devem ser positivos")
        if self.fps_num <= 0 or self.fps_den <= 0:
            raise ValueError("source.fps_num e source.fps_den devem ser positivos")
        if self.bit_depth not in (8, 16):
            raise ValueError("source.bit_depth deve ser 8 ou 16")
        if (
            self.expected_sequence_sha256 is not None
            and SHA256_PATTERN.fullmatch(self.expected_sequence_sha256) is None
        ):
            raise ValueError(
                "source.expected_sequence_sha256 deve ter 64 dígitos hexadecimais"
            )
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "base_url", self.base_url.rstrip("/") + "/")
        if self.expected_sequence_sha256 is not None:
            object.__setattr__(
                self,
                "expected_sequence_sha256",
                self.expected_sequence_sha256.lower(),
            )

    @property
    def last_frame(self) -> int:
        return self.first_frame + self.frame_count - 1

    @property
    def duration_s(self) -> float:
        return self.frame_count * self.fps_den / self.fps_num

    def filename(self, frame_number: int) -> str:
        return self.filename_pattern % frame_number


@dataclass(frozen=True)
class NormalizedClipConfig:
    output_yuv: Path
    provenance_path: Path
    width: int
    height: int
    pad_x: int
    pad_y: int
    pixel_format: str = "yuv420p"

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("clip.width e clip.height devem ser positivos")
        if self.width % 2 or self.height % 2:
            raise ValueError("YUV 4:2:0 exige largura e altura pares")
        if self.pad_x < 0 or self.pad_y < 0:
            raise ValueError("clip.pad_x e clip.pad_y não podem ser negativos")
        if self.pad_x % 2 or self.pad_y % 2:
            raise ValueError("clip.pad_x e clip.pad_y devem ser pares")
        if self.pixel_format != "yuv420p":
            raise ValueError("esta etapa exige clip.pixel_format=yuv420p")
        if self.output_yuv.suffix.lower() != ".yuv":
            raise ValueError("clip.output_yuv deve usar a extensão .yuv")
        if self.provenance_path.suffix.lower() != ".json":
            raise ValueError("clip.provenance_path deve usar a extensão .json")
        if self.output_yuv == self.provenance_path:
            raise ValueError("a saída YUV e a proveniência devem ser distintas")

    @property
    def frame_size_bytes(self) -> int:
        return self.width * self.height * 3 // 2


@dataclass(frozen=True)
class DownloadConfig:
    workers: int = 4
    timeout_s: float = 60.0
    retries: int = 3

    def __post_init__(self) -> None:
        if self.workers <= 0 or self.workers > 32:
            raise ValueError("download.workers deve estar entre 1 e 32")
        if self.timeout_s <= 0:
            raise ValueError("download.timeout_s deve ser positivo")
        if self.retries < 0:
            raise ValueError("download.retries não pode ser negativo")


@dataclass(frozen=True)
class PngSourcePreparationConfig:
    source_path: Path
    schema_version: int
    source: PngSequenceConfig
    clip: NormalizedClipConfig
    download: DownloadConfig
    ffmpeg_executable: str = "ffmpeg"

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"schema_version incompatível: esperado {SCHEMA_VERSION}"
            )
        if not self.ffmpeg_executable.strip():
            raise ValueError("ffmpeg_executable não pode ser vazio")
        if self.source.width + 2 * self.clip.pad_x != self.clip.width:
            raise ValueError("o padding horizontal não produz clip.width")
        if self.source.height + 2 * self.clip.pad_y != self.clip.height:
            raise ValueError("o padding vertical não produz clip.height")
        paths = {
            self.source.cache_dir,
            self.clip.output_yuv,
            self.clip.provenance_path,
        }
        if len(paths) != 3:
            raise ValueError("cache, saída YUV e proveniência devem ser distintos")


def _resolve(root: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def load_png_source_config(path: str | Path) -> PngSourcePreparationConfig:
    """Carrega o protocolo JSON e resolve caminhos relativos ao próprio arquivo."""

    source_path = Path(path).resolve()
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    root = source_path.parent
    source_raw = raw["source"]
    clip_raw = raw["clip"]
    download_raw = raw.get("download", {})
    return PngSourcePreparationConfig(
        source_path=source_path,
        schema_version=int(raw.get("schema_version", 0)),
        source=PngSequenceConfig(
            name=str(source_raw["name"]),
            base_url=str(source_raw["base_url"]),
            index_url=str(source_raw["index_url"]),
            license_name=str(source_raw["license_name"]),
            license_url=str(source_raw["license_url"]),
            cache_dir=_resolve(root, str(source_raw["cache_dir"])),
            filename_pattern=str(source_raw["filename_pattern"]),
            first_frame=int(source_raw["first_frame"]),
            frame_count=int(source_raw["frame_count"]),
            width=int(source_raw["width"]),
            height=int(source_raw["height"]),
            fps_num=int(source_raw["fps_num"]),
            fps_den=int(source_raw.get("fps_den", 1)),
            bit_depth=int(source_raw.get("bit_depth", 8)),
            expected_sequence_sha256=(
                str(source_raw["expected_sequence_sha256"])
                if source_raw.get("expected_sequence_sha256") is not None
                else None
            ),
        ),
        clip=NormalizedClipConfig(
            output_yuv=_resolve(root, str(clip_raw["output_yuv"])),
            provenance_path=_resolve(root, str(clip_raw["provenance_path"])),
            width=int(clip_raw["width"]),
            height=int(clip_raw["height"]),
            pad_x=int(clip_raw["pad_x"]),
            pad_y=int(clip_raw["pad_y"]),
            pixel_format=str(clip_raw.get("pixel_format", "yuv420p")),
        ),
        download=DownloadConfig(
            workers=int(download_raw.get("workers", 4)),
            timeout_s=float(download_raw.get("timeout_s", 60.0)),
            retries=int(download_raw.get("retries", 3)),
        ),
        ffmpeg_executable=str(raw.get("ffmpeg_executable", "ffmpeg")),
    )


def with_path_overrides(
    config: PngSourcePreparationConfig,
    *,
    cache_dir: str | Path | None = None,
    output_yuv: str | Path | None = None,
    provenance_path: str | Path | None = None,
    ffmpeg_executable: str | None = None,
) -> PngSourcePreparationConfig:
    """Aplica caminhos locais sem alterar o protocolo versionado."""

    source = PngSequenceConfig(
        **{
            **asdict(config.source),
            "cache_dir": (
                Path(cache_dir).expanduser().resolve()
                if cache_dir is not None
                else config.source.cache_dir
            ),
        }
    )
    clip = NormalizedClipConfig(
        **{
            **asdict(config.clip),
            "output_yuv": (
                Path(output_yuv).expanduser().resolve()
                if output_yuv is not None
                else config.clip.output_yuv
            ),
            "provenance_path": (
                Path(provenance_path).expanduser().resolve()
                if provenance_path is not None
                else config.clip.provenance_path
            ),
        }
    )
    return PngSourcePreparationConfig(
        source_path=config.source_path,
        schema_version=config.schema_version,
        source=source,
        clip=clip,
        download=config.download,
        ffmpeg_executable=(
            ffmpeg_executable
            if ffmpeg_executable is not None
            else config.ffmpeg_executable
        ),
    )


def parse_png_header(path: str | Path) -> dict[str, int]:
    """Lê IHDR suficiente para rejeitar arquivos truncados ou incompatíveis."""

    with Path(path).open("rb") as handle:
        header = handle.read(29)
    if len(header) != 29 or header[:8] != PNG_SIGNATURE:
        raise ValueError(f"arquivo não é um PNG válido: {path}")
    length = struct.unpack(">I", header[8:12])[0]
    if length != 13 or header[12:16] != b"IHDR":
        raise ValueError(f"IHDR PNG inválido: {path}")
    width, height = struct.unpack(">II", header[16:24])
    return {
        "width": width,
        "height": height,
        "bit_depth": header[24],
        "color_type": header[25],
        "compression_method": header[26],
        "filter_method": header[27],
        "interlace_method": header[28],
    }


def _validate_png(path: Path, source: PngSequenceConfig) -> dict[str, int]:
    header = parse_png_header(path)
    actual = (header["width"], header["height"], header["bit_depth"])
    expected = (source.width, source.height, source.bit_depth)
    if actual != expected:
        raise ValueError(
            f"PNG incompatível em {path}: detectado={actual}, esperado={expected}"
        )
    if header["compression_method"] != 0 or header["filter_method"] != 0:
        raise ValueError(f"método PNG não suportado em {path}")
    return header


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_file(url: str, destination: Path, timeout_s: float, retries: int) -> None:
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "tcc-vvc-qlearning-scripts/1.0"},
    )
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                if getattr(response, "status", 200) != 200:
                    raise RuntimeError(f"HTTP {response.status} para {url}")
                with temporary.open("wb") as handle:
                    shutil.copyfileobj(response, handle, length=1024 * 1024)
            temporary.replace(destination)
            return
        except (OSError, RuntimeError, urllib.error.URLError):
            temporary.unlink(missing_ok=True)
            if attempt == retries:
                raise
            time.sleep(min(2**attempt, 8))


def _frame_url(source: PngSequenceConfig, frame_number: int) -> str:
    return urljoin(source.base_url, source.filename(frame_number))


def _download_and_validate(
    source: PngSequenceConfig,
    frame_number: int,
    downloader: FrameDownloader,
    timeout_s: float,
    retries: int,
) -> None:
    destination = source.cache_dir / source.filename(frame_number)
    downloader(_frame_url(source, frame_number), destination, timeout_s, retries)
    try:
        _validate_png(destination, source)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def _collect_frames(
    config: PngSourcePreparationConfig,
    *,
    redownload: bool,
    downloader: FrameDownloader,
    progress: ProgressReporter | None,
) -> tuple[list[dict[str, object]], int, int]:
    source = config.source
    source.cache_dir.mkdir(parents=True, exist_ok=True)
    frame_numbers = range(source.first_frame, source.last_frame + 1)
    pending: list[int] = []
    reused = 0
    for frame_number in frame_numbers:
        path = source.cache_dir / source.filename(frame_number)
        if path.exists() and not redownload:
            _validate_png(path, source)
            reused += 1
        else:
            pending.append(frame_number)

    if progress is not None:
        progress(
            f"quadros no cache={reused}; quadros a baixar={len(pending)}; "
            f"intervalo={source.first_frame:05d}..{source.last_frame:05d}"
        )
    completed = 0
    with ThreadPoolExecutor(max_workers=config.download.workers) as executor:
        futures = {
            executor.submit(
                _download_and_validate,
                source,
                frame_number,
                downloader,
                config.download.timeout_s,
                config.download.retries,
            ): frame_number
            for frame_number in pending
        }
        for future in as_completed(futures):
            frame_number = futures[future]
            try:
                future.result()
            except BaseException as exc:
                raise RuntimeError(
                    f"falha ao obter o quadro {frame_number:05d}"
                ) from exc
            completed += 1
            if progress is not None and (
                completed == len(pending) or completed % 25 == 0
            ):
                progress(f"download: {completed}/{len(pending)}")

    records: list[dict[str, object]] = []
    aggregate = hashlib.sha256()
    for frame_number in frame_numbers:
        filename = source.filename(frame_number)
        path = source.cache_dir / filename
        header = _validate_png(path, source)
        size_bytes = path.stat().st_size
        frame_sha256 = _sha256(path)
        aggregate.update(
            f"{filename}\t{size_bytes}\t{frame_sha256}\n".encode("ascii")
        )
        records.append(
            {
                "frame_number": frame_number,
                "filename": filename,
                "size_bytes": size_bytes,
                "sha256": frame_sha256,
                "png": header,
            }
        )
    sequence_sha256 = aggregate.hexdigest()
    expected = source.expected_sequence_sha256
    if expected is not None and sequence_sha256 != expected:
        raise ValueError(
            "SHA-256 agregado da sequência não confere: "
            f"detectado={sequence_sha256}, esperado={expected}"
        )
    return records, completed, reused


def _resolve_tool(executable: str) -> str:
    candidate = Path(executable).expanduser()
    if candidate.parent != Path(".") or candidate.is_absolute():
        if not candidate.is_file():
            raise FileNotFoundError(f"executável não encontrado: {candidate}")
        return str(candidate.resolve())
    resolved = shutil.which(executable)
    if resolved is None:
        raise FileNotFoundError(f"executável '{executable}' não encontrado no PATH")
    return resolved


def _tool_version(executable: str, runner: CommandRunner) -> str:
    completed = runner(
        [executable, "-version"],
        check=False,
        capture_output=True,
        text=True,
    )
    output = "\n".join(
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if part.strip()
    )
    if completed.returncode != 0 or not output:
        return "não informado pelo executável"
    return output.splitlines()[0]


def build_ffmpeg_command(
    config: PngSourcePreparationConfig,
    executable: str,
    destination: Path,
) -> list[str]:
    source = config.source
    clip = config.clip
    return [
        executable,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-framerate",
        f"{source.fps_num}/{source.fps_den}",
        "-start_number",
        str(source.first_frame),
        "-i",
        str(source.cache_dir / source.filename_pattern),
        "-map",
        "0:v:0",
        "-vf",
        (
            f"pad={clip.width}:{clip.height}:{clip.pad_x}:{clip.pad_y}:"
            f"color=black,format={clip.pixel_format}"
        ),
        "-frames:v",
        str(source.frame_count),
        "-fps_mode",
        "passthrough",
        "-f",
        "rawvideo",
        str(destination),
    ]


def _pipeline_metadata() -> dict[str, object]:
    module_path = Path(__file__).resolve()
    metadata: dict[str, object] = {
        "module": str(module_path),
        "module_sha256": _sha256(module_path),
        "git_commit": None,
        "git_dirty": None,
    }
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=module_path.parent,
            check=False,
            capture_output=True,
            text=True,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=module_path.parent,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return metadata
    if revision.returncode == 0:
        metadata["git_commit"] = revision.stdout.strip()
    if status.returncode == 0:
        metadata["git_dirty"] = bool(status.stdout.strip())
    return metadata


def _normalized_config(config: PngSourcePreparationConfig) -> dict[str, object]:
    return {
        "schema_version": config.schema_version,
        "source": {
            **asdict(config.source),
            "cache_dir": str(config.source.cache_dir),
        },
        "clip": {
            **asdict(config.clip),
            "output_yuv": str(config.clip.output_yuv),
            "provenance_path": str(config.clip.provenance_path),
        },
        "download": asdict(config.download),
        "ffmpeg_executable": config.ffmpeg_executable,
    }


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def prepare_png_source(
    config: PngSourcePreparationConfig,
    *,
    overwrite: bool = False,
    redownload: bool = False,
    runner: CommandRunner = subprocess.run,
    downloader: FrameDownloader = _download_file,
    ffmpeg_info: dict[str, str] | None = None,
    progress: ProgressReporter | None = None,
) -> dict[str, object]:
    """Obtém os quadros exatos, verifica-os e gera um YUV letterboxed."""

    clip = config.clip
    if not overwrite:
        for path in (clip.output_yuv, clip.provenance_path):
            if path.exists():
                raise FileExistsError(
                    f"arquivo já existe: {path}; use --overwrite conscientemente"
                )

    records, downloaded, reused = _collect_frames(
        config,
        redownload=redownload,
        downloader=downloader,
        progress=progress,
    )
    aggregate_sha256 = hashlib.sha256()
    for record in records:
        aggregate_sha256.update(
            (
                f"{record['filename']}\t{record['size_bytes']}\t"
                f"{record['sha256']}\n"
            ).encode("ascii")
        )
    sequence_sha256 = aggregate_sha256.hexdigest()

    tool = ffmpeg_info
    if tool is None:
        executable = _resolve_tool(config.ffmpeg_executable)
        tool = {
            "path": executable,
            "version": _tool_version(executable, runner),
        }
    else:
        executable = tool["path"]

    clip.output_yuv.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = clip.output_yuv.with_suffix(clip.output_yuv.suffix + ".tmp")
    temporary_output.unlink(missing_ok=True)
    command = build_ffmpeg_command(config, executable, temporary_output)
    if progress is not None:
        progress(
            f"normalizando {config.source.width}x{config.source.height} para "
            f"{clip.width}x{clip.height} com padding ({clip.pad_x}, {clip.pad_y})"
        )
    try:
        completed = runner(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except BaseException:
        temporary_output.unlink(missing_ok=True)
        raise
    if completed.returncode != 0:
        temporary_output.unlink(missing_ok=True)
        details = "\n".join(
            part.strip()
            for part in (completed.stdout, completed.stderr)
            if part.strip()
        )
        raise RuntimeError(
            f"FFmpeg falhou com código {completed.returncode}: {details}"
        )

    expected_size = clip.frame_size_bytes * config.source.frame_count
    actual_size = temporary_output.stat().st_size if temporary_output.exists() else 0
    if actual_size != expected_size:
        temporary_output.unlink(missing_ok=True)
        raise RuntimeError(
            "tamanho inesperado da saída YUV: "
            f"detectado={actual_size}, esperado={expected_size}"
        )
    temporary_output.replace(clip.output_yuv)
    output_sha256 = _sha256(clip.output_yuv)

    provenance = {
        "preparation_schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "configuration_file": str(config.source_path),
        "configuration_sha256": _sha256(config.source_path),
        "configuration": _normalized_config(config),
        "source_sequence": {
            "name": config.source.name,
            "base_url": config.source.base_url,
            "index_url": config.source.index_url,
            "license_name": config.source.license_name,
            "license_url": config.source.license_url,
            "first_frame": config.source.first_frame,
            "last_frame": config.source.last_frame,
            "frame_count": config.source.frame_count,
            "width": config.source.width,
            "height": config.source.height,
            "fps_num": config.source.fps_num,
            "fps_den": config.source.fps_den,
            "duration_s": config.source.duration_s,
            "total_size_bytes": sum(int(record["size_bytes"]) for record in records),
            "sequence_sha256": sequence_sha256,
            "expected_sequence_sha256": config.source.expected_sequence_sha256,
            "integrity_pinned": config.source.expected_sequence_sha256 is not None,
            "downloaded_frames": downloaded,
            "reused_frames": reused,
            "frames": records,
        },
        "normalization": {
            "policy": "symmetric_letterbox",
            "pad_x": clip.pad_x,
            "pad_y": clip.pad_y,
            "color": "black",
            "active_region": {
                "x": clip.pad_x,
                "y": clip.pad_y,
                "width": config.source.width,
                "height": config.source.height,
            },
            "ffmpeg": tool,
            "command": command,
        },
        "clip": {
            "path": str(clip.output_yuv),
            "width": clip.width,
            "height": clip.height,
            "pixel_format": clip.pixel_format,
            "frame_count": config.source.frame_count,
            "duration_s": config.source.duration_s,
            "size_bytes": actual_size,
            "sha256": output_sha256,
        },
        "pipeline": _pipeline_metadata(),
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
    }
    _write_json_atomic(clip.provenance_path, provenance)
    return provenance
