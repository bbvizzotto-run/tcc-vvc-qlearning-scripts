"""Pipeline reprodutível para codificar e medir segmentos VVC independentes."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Callable, Sequence

from qoe_metrics import calculate_psnr_yuv_segment
from segment_manifest import load_segment_manifest


SCHEMA_VERSION = 1
MANIFEST_FIELDS = (
    "sequence",
    "segment",
    "bitrate_kbps",
    "duration_s",
    "size_bytes",
    "psnr_y_db",
    "source_file",
    "sha256",
)
VALID_PRESETS = {"faster", "fast", "medium", "slow", "slower"}
VALID_FORMATS = {8: "yuv420", 10: "yuv420_10"}
SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
VERSION_PATTERN = re.compile(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?")


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
ProgressReporter = Callable[[str], None]


@dataclass(frozen=True)
class SourceConfig:
    name: str
    input_yuv: Path
    width: int
    height: int
    fps_num: int
    fps_den: int
    bit_depth: int
    start_frame: int
    segment_count: int
    segment_duration_s: float

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("sequence.name não pode ser vazio")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width e height devem ser positivos")
        if self.width % 2 or self.height % 2:
            raise ValueError("YUV 4:2:0 exige largura e altura pares")
        if self.fps_num <= 0 or self.fps_den <= 0:
            raise ValueError("fps_num e fps_den devem ser positivos")
        if self.bit_depth not in VALID_FORMATS:
            raise ValueError("bit_depth deve ser 8 ou 10 para YUV 4:2:0")
        if self.start_frame < 0:
            raise ValueError("start_frame não pode ser negativo")
        if self.segment_count <= 0:
            raise ValueError("segment_count deve ser positivo")
        if not math.isfinite(self.segment_duration_s) or self.segment_duration_s <= 0:
            raise ValueError("segment_duration_s deve ser positivo e finito")
        object.__setattr__(self, "name", self.name.strip())

    @property
    def fps(self) -> Fraction:
        return Fraction(self.fps_num, self.fps_den)

    @property
    def frames_per_segment(self) -> int:
        duration = Fraction(str(self.segment_duration_s))
        frames = duration * self.fps
        if frames.denominator != 1:
            raise ValueError(
                "segment_duration_s × fps deve resultar em número inteiro de quadros"
            )
        return int(frames)

    @property
    def total_required_frames(self) -> int:
        return self.start_frame + self.segment_count * self.frames_per_segment

    @property
    def frame_size_bytes(self) -> int:
        bytes_per_sample = 1 if self.bit_depth == 8 else 2
        return self.width * self.height * 3 // 2 * bytes_per_sample

    @property
    def format_name(self) -> str:
        return VALID_FORMATS[self.bit_depth]


@dataclass(frozen=True)
class EncoderConfig:
    executable: str = "vvencapp"
    preset: str = "medium"
    passes: int = 2
    qpa: bool = True
    internal_bit_depth: int | None = None
    refresh_type: str = "idr_no_radl"
    poc0idr: bool = True
    threads: int | None = None
    mt_profile: int = 0
    minimum_version: str = "1.13.0"

    def __post_init__(self) -> None:
        if not self.executable.strip():
            raise ValueError("encoder.executable não pode ser vazio")
        if self.preset not in VALID_PRESETS:
            raise ValueError(
                "encoder.preset deve ser faster, fast, medium, slow ou slower"
            )
        if self.passes not in (1, 2):
            raise ValueError("encoder.passes deve ser 1 ou 2")
        if self.internal_bit_depth not in (None, 8, 10):
            raise ValueError("encoder.internal_bit_depth deve ser 8 ou 10")
        if not self.refresh_type.strip():
            raise ValueError("encoder.refresh_type não pode ser vazio")
        if (
            self.refresh_type.strip().lower() == "idr_no_radl"
            and not self.poc0idr
        ):
            raise ValueError(
                "encoder.poc0idr deve ser true quando refresh_type é idr_no_radl"
            )
        if self.threads is not None and self.threads <= 0:
            raise ValueError("encoder.threads deve ser positivo")
        if self.mt_profile not in (0, 1, 2, 3):
            raise ValueError("encoder.mt_profile deve estar entre 0 e 3")
        if re.fullmatch(r"\d+\.\d+(?:\.\d+)?", self.minimum_version) is None:
            raise ValueError("encoder.minimum_version deve usar o formato X.Y ou X.Y.Z")


@dataclass(frozen=True)
class QualityRegionConfig:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.x < 0 or self.y < 0:
            raise ValueError("decoder.quality_region x e y não podem ser negativos")
        if self.width <= 0 or self.height <= 0:
            raise ValueError(
                "decoder.quality_region width e height devem ser positivos"
            )


@dataclass(frozen=True)
class DecoderConfig:
    executable: str = "vvdecapp"
    compute_psnr_y: bool = True
    keep_reconstructions: bool = False
    quality_region: QualityRegionConfig | None = None

    def __post_init__(self) -> None:
        if self.compute_psnr_y and not self.executable.strip():
            raise ValueError("decoder.executable é obrigatório para calcular PSNR-Y")
        if not self.compute_psnr_y and self.quality_region is not None:
            raise ValueError(
                "decoder.quality_region exige decoder.compute_psnr_y=true"
            )


@dataclass(frozen=True)
class PipelineConfig:
    source_path: Path
    schema_version: int
    source: SourceConfig
    bitrates_kbps: tuple[int, ...]
    output_dir: Path
    manifest_path: Path
    encoder: EncoderConfig
    decoder: DecoderConfig
    hash_source: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"schema_version incompatível: esperado {SCHEMA_VERSION}"
            )
        if not self.bitrates_kbps:
            raise ValueError("bitrates_kbps não pode ser vazio")
        if any(bitrate <= 0 for bitrate in self.bitrates_kbps):
            raise ValueError("todos os bitrates devem ser positivos")
        if len(set(self.bitrates_kbps)) != len(self.bitrates_kbps):
            raise ValueError("bitrates_kbps não pode conter duplicatas")
        if tuple(sorted(self.bitrates_kbps)) != self.bitrates_kbps:
            raise ValueError("bitrates_kbps deve estar em ordem crescente")
        internal_depth = self.encoder.internal_bit_depth or self.source.bit_depth
        if internal_depth != self.source.bit_depth:
            raise ValueError(
                "nesta etapa, internal_bit_depth deve coincidir com o bit depth da fonte "
                "para que o PSNR-Y use a mesma representação de amostras"
            )
        if self.output_dir == self.manifest_path:
            raise ValueError("output_dir e manifest_path não podem ser iguais")
        if self.manifest_path.suffix.lower() != ".csv":
            raise ValueError("manifest_path deve usar a extensão .csv")
        quality_region = self.decoder.quality_region
        if quality_region is not None and (
            quality_region.x + quality_region.width > self.source.width
            or quality_region.y + quality_region.height > self.source.height
        ):
            raise ValueError(
                "decoder.quality_region deve estar contida no quadro da fonte"
            )
        self.source.frames_per_segment


@dataclass(frozen=True)
class EncodingJob:
    segment: int
    bitrate_kbps: int
    frame_skip: int
    frames: int
    duration_s: float
    bitstream_path: Path
    reconstruction_path: Path | None
    log_path: Path


def _resolve(root: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def load_pipeline_config(path: str | Path) -> PipelineConfig:
    """Carrega uma configuração JSON e resolve caminhos relativos ao arquivo."""

    source_path = Path(path).resolve()
    with source_path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    root = source_path.parent
    source_raw = raw["source"]
    encoder_raw = raw.get("encoder", {})
    decoder_raw = raw.get("decoder", {})
    quality_region_raw = decoder_raw.get("quality_region")

    source = SourceConfig(
        name=str(source_raw["name"]),
        input_yuv=_resolve(root, source_raw["input_yuv"]),
        width=int(source_raw["width"]),
        height=int(source_raw["height"]),
        fps_num=int(source_raw["fps_num"]),
        fps_den=int(source_raw.get("fps_den", 1)),
        bit_depth=int(source_raw.get("bit_depth", 8)),
        start_frame=int(source_raw.get("start_frame", 0)),
        segment_count=int(source_raw["segment_count"]),
        segment_duration_s=float(source_raw.get("segment_duration_s", 2.0)),
    )
    encoder = EncoderConfig(
        executable=str(encoder_raw.get("executable", "vvencapp")),
        preset=str(encoder_raw.get("preset", "medium")),
        passes=int(encoder_raw.get("passes", 2)),
        qpa=bool(encoder_raw.get("qpa", True)),
        internal_bit_depth=(
            int(encoder_raw["internal_bit_depth"])
            if encoder_raw.get("internal_bit_depth") is not None
            else source.bit_depth
        ),
        refresh_type=str(encoder_raw.get("refresh_type", "idr_no_radl")),
        poc0idr=bool(encoder_raw.get("poc0idr", True)),
        threads=(
            int(encoder_raw["threads"])
            if encoder_raw.get("threads") is not None
            else None
        ),
        mt_profile=int(encoder_raw.get("mt_profile", 0)),
        minimum_version=str(encoder_raw.get("minimum_version", "1.13.0")),
    )
    decoder = DecoderConfig(
        executable=str(decoder_raw.get("executable", "vvdecapp")),
        compute_psnr_y=bool(decoder_raw.get("compute_psnr_y", True)),
        keep_reconstructions=bool(
            decoder_raw.get("keep_reconstructions", False)
        ),
        quality_region=(
            QualityRegionConfig(
                x=int(quality_region_raw["x"]),
                y=int(quality_region_raw["y"]),
                width=int(quality_region_raw["width"]),
                height=int(quality_region_raw["height"]),
            )
            if quality_region_raw is not None
            else None
        ),
    )
    return PipelineConfig(
        source_path=source_path,
        schema_version=int(raw.get("schema_version", 0)),
        source=source,
        bitrates_kbps=tuple(int(value) for value in raw["bitrates_kbps"]),
        output_dir=_resolve(root, raw["output_dir"]),
        manifest_path=_resolve(root, raw["manifest_path"]),
        encoder=encoder,
        decoder=decoder,
        hash_source=bool(raw.get("hash_source", True)),
    )


def _safe_name(name: str) -> str:
    normalized = SAFE_NAME_PATTERN.sub("_", name.strip()).strip("._")
    if not normalized:
        raise ValueError("o nome da sequência não produz um caminho seguro")
    return normalized


def build_jobs(config: PipelineConfig) -> list[EncodingJob]:
    """Expande a configuração na matriz segmento × representação."""

    sequence_dir = config.output_dir / _safe_name(config.source.name)
    jobs: list[EncodingJob] = []
    for bitrate in config.bitrates_kbps:
        representation_dir = sequence_dir / f"bitrate_{bitrate:06d}kbps"
        for segment in range(config.source.segment_count):
            stem = f"segment_{segment:04d}"
            jobs.append(
                EncodingJob(
                    segment=segment,
                    bitrate_kbps=bitrate,
                    frame_skip=(
                        config.source.start_frame
                        + segment * config.source.frames_per_segment
                    ),
                    frames=config.source.frames_per_segment,
                    duration_s=config.source.segment_duration_s,
                    bitstream_path=representation_dir / f"{stem}.266",
                    reconstruction_path=(
                        representation_dir / f"{stem}.recon.yuv"
                        if config.decoder.compute_psnr_y
                        else None
                    ),
                    log_path=representation_dir / f"{stem}.log",
                )
            )
    return jobs


def build_encoder_command(config: PipelineConfig, job: EncodingJob) -> list[str]:
    internal_depth = config.encoder.internal_bit_depth or config.source.bit_depth
    command = [
        config.encoder.executable,
        "--input",
        str(config.source.input_yuv),
        "--size",
        f"{config.source.width}x{config.source.height}",
        "--fps",
        f"{config.source.fps_num}/{config.source.fps_den}",
        "--format",
        config.source.format_name,
        "--internal-bitdepth",
        str(internal_depth),
        "--frameskip",
        str(job.frame_skip),
        "--frames",
        str(job.frames),
        "--preset",
        config.encoder.preset,
        "--bitrate",
        str(job.bitrate_kbps * 1000),
        "--passes",
        str(config.encoder.passes),
        "--qpa",
        "1" if config.encoder.qpa else "0",
        "--refreshtype",
        config.encoder.refresh_type,
        "--additional",
        f"POC0IDR={1 if config.encoder.poc0idr else 0}",
        "--mtprofile",
        str(config.encoder.mt_profile),
    ]
    if config.encoder.threads is not None:
        command.extend(("--threads", str(config.encoder.threads)))
    command.extend(("--output", str(job.bitstream_path)))
    return command


def build_decoder_command(config: PipelineConfig, job: EncodingJob) -> list[str]:
    if job.reconstruction_path is None:
        raise ValueError("o job não solicita reconstrução")
    return [
        config.decoder.executable,
        "--bitstream",
        str(job.bitstream_path),
        "--output",
        str(job.reconstruction_path),
    ]


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _available_frames(source: SourceConfig) -> int:
    size = source.input_yuv.stat().st_size
    if size % source.frame_size_bytes:
        raise ValueError(
            "o tamanho da fonte não é múltiplo do tamanho de um quadro YUV 4:2:0; "
            "confira resolução e profundidade de bits"
        )
    return size // source.frame_size_bytes


def validate_source(config: PipelineConfig) -> dict[str, object]:
    """Confirma existência, layout e quantidade de quadros da fonte YUV."""

    source = config.source
    if not source.input_yuv.is_file():
        raise FileNotFoundError(f"fonte YUV não encontrada: {source.input_yuv}")
    frames = _available_frames(source)
    if frames < source.total_required_frames:
        available_after_start = max(frames - source.start_frame, 0)
        available_segments = available_after_start // source.frames_per_segment
        raise ValueError(
            "a fonte não contém quadros suficientes: "
            f"necessários={source.total_required_frames}, disponíveis={frames}, "
            f"segmentos completos após start_frame={available_segments}. "
            "O pipeline não repete conteúdo automaticamente."
        )
    return {
        "path": str(source.input_yuv),
        "size_bytes": source.input_yuv.stat().st_size,
        "available_frames": frames,
        "required_frames": source.total_required_frames,
        "sha256": _sha256(source.input_yuv) if config.hash_source else None,
    }


def _resolve_tool(executable: str) -> str:
    candidate = Path(executable).expanduser()
    if candidate.parent != Path(".") or candidate.is_absolute():
        if not candidate.is_file():
            raise FileNotFoundError(f"executável não encontrado: {candidate}")
        return str(candidate.resolve())
    resolved = shutil.which(executable)
    if resolved is None:
        raise FileNotFoundError(
            f"executável '{executable}' não encontrado no PATH"
        )
    return resolved


def _tool_version(executable: str, runner: CommandRunner) -> str:
    completed = runner(
        [executable, "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    if completed.returncode != 0 or not output:
        return "não informado pelo executável"
    return output.splitlines()[0]


def _parse_version(value: str) -> tuple[int, int, int] | None:
    match = VERSION_PATTERN.search(value)
    if match is None:
        return None
    return tuple(int(part or 0) for part in match.groups())


def preflight_tools(
    config: PipelineConfig,
    runner: CommandRunner = subprocess.run,
) -> dict[str, dict[str, str]]:
    encoder_path = _resolve_tool(config.encoder.executable)
    encoder_version = _tool_version(encoder_path, runner)
    detected = _parse_version(encoder_version)
    minimum = _parse_version(config.encoder.minimum_version)
    if detected is not None and minimum is not None and detected < minimum:
        raise ValueError(
            "versão do VVenC abaixo da mínima configurada: "
            f"detectada={encoder_version}, mínima={config.encoder.minimum_version}"
        )
    tools = {
        "encoder": {"path": encoder_path, "version": encoder_version},
    }
    if config.decoder.compute_psnr_y:
        decoder_path = _resolve_tool(config.decoder.executable)
        tools["decoder"] = {
            "path": decoder_path,
            "version": _tool_version(decoder_path, runner),
        }
    return tools


def _replace_executable(command: Sequence[str], executable: str) -> list[str]:
    return [executable, *command[1:]]


def _run_command(
    command: Sequence[str],
    log_path: Path,
    runner: CommandRunner,
) -> None:
    completed = runner(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "$ " + shlex.join(command) + "\n\n"
        + (completed.stdout or "")
        + ("\n[stderr]\n" + completed.stderr if completed.stderr else ""),
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"comando falhou com código {completed.returncode}; consulte {log_path}"
        )


def _logical_source_path(manifest_path: Path, bitstream_path: Path) -> str:
    return Path(os.path.relpath(bitstream_path, manifest_path.parent)).as_posix()


def _write_manifest(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _normalized_config(config: PipelineConfig) -> dict[str, object]:
    source = asdict(config.source)
    source["input_yuv"] = str(config.source.input_yuv)
    return {
        "schema_version": config.schema_version,
        "source": source,
        "bitrates_kbps": list(config.bitrates_kbps),
        "output_dir": str(config.output_dir),
        "manifest_path": str(config.manifest_path),
        "encoder": asdict(config.encoder),
        "decoder": asdict(config.decoder),
        "hash_source": config.hash_source,
    }


def _provenance_path(manifest_path: Path) -> Path:
    return manifest_path.with_suffix(".provenance.json")


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


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_dry_run_plan(config: PipelineConfig) -> dict[str, object]:
    """Produz comandos determinísticos sem exigir fonte ou executáveis instalados."""

    jobs = build_jobs(config)
    return {
        "dry_run": True,
        "configuration": _normalized_config(config),
        "job_count": len(jobs),
        "manifest_path": str(config.manifest_path),
        "jobs": [
            {
                "segment": job.segment,
                "bitrate_kbps": job.bitrate_kbps,
                "encoder_command": build_encoder_command(config, job),
                "decoder_command": (
                    build_decoder_command(config, job)
                    if config.decoder.compute_psnr_y
                    else None
                ),
            }
            for job in jobs
        ],
    }


def execute_pipeline(
    config: PipelineConfig,
    *,
    overwrite: bool = False,
    resume: bool = False,
    runner: CommandRunner = subprocess.run,
    tools: dict[str, dict[str, str]] | None = None,
    progress: ProgressReporter | None = None,
) -> dict[str, object]:
    """Codifica a matriz, mede os artefatos e grava manifesto e proveniência."""

    if overwrite and resume:
        raise ValueError("--overwrite e --resume são mutuamente exclusivos")
    if config.manifest_path.exists() and not overwrite:
        raise FileExistsError(
            f"o manifesto já existe: {config.manifest_path}; use --overwrite conscientemente"
        )
    provenance_path = _provenance_path(config.manifest_path)
    if provenance_path.exists() and not overwrite:
        raise FileExistsError(
            f"a proveniência já existe: {provenance_path}; "
            "use --overwrite conscientemente"
        )
    source_metadata = validate_source(config)
    tool_metadata = tools or preflight_tools(config, runner)
    pipeline_metadata = _pipeline_metadata()
    jobs = build_jobs(config)
    if not overwrite and not resume:
        expected_paths: list[Path] = []
        for job in jobs:
            expected_paths.extend((job.bitstream_path, job.log_path))
            if job.reconstruction_path is not None:
                expected_paths.extend(
                    (
                        job.reconstruction_path,
                        job.log_path.with_name(job.log_path.stem + ".decode.log"),
                    )
                )
        existing = [path for path in expected_paths if path.exists()]
        if existing:
            raise FileExistsError(
                f"artefato já existe: {existing[0]}; use --overwrite conscientemente"
            )
    rows: list[dict[str, object]] = []
    commands: list[dict[str, object]] = []

    for job_index, job in enumerate(jobs, start=1):
        if progress is not None:
            progress(
                f"[{job_index}/{len(jobs)}] segmento={job.segment} "
                f"bitrate={job.bitrate_kbps} kbps"
            )
        job.bitstream_path.parent.mkdir(parents=True, exist_ok=True)
        encoder_command = _replace_executable(
            build_encoder_command(config, job),
            tool_metadata["encoder"]["path"],
        )
        expected_log_header = "$ " + shlex.join(encoder_command)
        encoder_reused = False
        if resume and job.bitstream_path.exists():
            if job.bitstream_path.stat().st_size <= 0 or not job.log_path.is_file():
                raise RuntimeError(
                    "não é possível retomar um artefato vazio ou sem log: "
                    f"{job.bitstream_path}"
                )
            log_lines = job.log_path.read_text(encoding="utf-8").splitlines()
            if not log_lines or log_lines[0] != expected_log_header:
                raise RuntimeError(
                    "o comando do artefato existente difere da configuração atual: "
                    f"{job.bitstream_path}"
                )
            encoder_reused = True
        else:
            _run_command(encoder_command, job.log_path, runner)
        if not job.bitstream_path.is_file() or job.bitstream_path.stat().st_size <= 0:
            raise RuntimeError(
                f"o VVenC não produziu um bitstream válido: {job.bitstream_path}"
            )

        decoder_command: list[str] | None = None
        psnr_y_db: float | None = None
        if config.decoder.compute_psnr_y:
            decoder_command = _replace_executable(
                build_decoder_command(config, job),
                tool_metadata["decoder"]["path"],
            )
            decoder_log = job.log_path.with_name(job.log_path.stem + ".decode.log")
            _run_command(decoder_command, decoder_log, runner)
            reconstruction = job.reconstruction_path
            if reconstruction is None or not reconstruction.is_file():
                raise RuntimeError("o VVdeC não produziu a reconstrução esperada")
            psnr_y_db = calculate_psnr_yuv_segment(
                config.source.input_yuv,
                reconstruction,
                config.source.width,
                config.source.height,
                job.frames,
                original_start_frame=job.frame_skip,
                bit_depth=config.source.bit_depth,
                quality_region=(
                    (
                        config.decoder.quality_region.x,
                        config.decoder.quality_region.y,
                        config.decoder.quality_region.width,
                        config.decoder.quality_region.height,
                    )
                    if config.decoder.quality_region is not None
                    else None
                ),
            )
            if not config.decoder.keep_reconstructions:
                reconstruction.unlink()

        rows.append(
            {
                "sequence": config.source.name,
                "segment": job.segment,
                "bitrate_kbps": job.bitrate_kbps,
                "duration_s": f"{job.duration_s:.9g}",
                "size_bytes": job.bitstream_path.stat().st_size,
                "psnr_y_db": (
                    f"{psnr_y_db:.6f}" if psnr_y_db is not None else ""
                ),
                "source_file": _logical_source_path(
                    config.manifest_path,
                    job.bitstream_path,
                ),
                "sha256": _sha256(job.bitstream_path),
            }
        )
        commands.append(
            {
                "segment": job.segment,
                "bitrate_kbps": job.bitrate_kbps,
                "encoder": encoder_command,
                "encoder_reused": encoder_reused,
                "decoder": decoder_command,
            }
        )

    rows.sort(key=lambda row: (int(row["segment"]), int(row["bitrate_kbps"])))
    _write_manifest(config.manifest_path, rows)
    manifest = load_segment_manifest(config.manifest_path)
    provenance = {
        "pipeline_schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "configuration_file": str(config.source_path),
        "configuration_sha256": _sha256(config.source_path),
        "configuration": _normalized_config(config),
        "pipeline": pipeline_metadata,
        "source": source_metadata,
        "tools": tool_metadata,
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "commands": commands,
        "manifest": manifest.metadata(),
    }
    _write_json_atomic(provenance_path, provenance)
    return {
        "dry_run": False,
        "manifest": str(config.manifest_path),
        "provenance": str(provenance_path),
        "segments": manifest.segment_count,
        "representations": len(manifest.bitrates_kbps),
        "artifacts": len(rows),
        "manifest_sha256": manifest.manifest_sha256,
    }
