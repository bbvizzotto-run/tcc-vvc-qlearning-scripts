"""Preparação reproduzível de trechos YUV a partir de fontes Y4M/XZ."""

from __future__ import annotations

import errno
import hashlib
import json
import lzma
import platform
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence


SCHEMA_VERSION = 1
SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")
SUPPORTED_CHROMA = {"420", "420jpeg", "420mpeg2", "420paldv"}

PopenFactory = Callable[..., subprocess.Popen[bytes]]
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
ProgressReporter = Callable[[str], None]


@dataclass(frozen=True)
class SourceArchiveConfig:
    name: str
    url: str
    license_name: str
    license_url: str
    input_xz: Path
    expected_sha256: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("source.name não pode ser vazio")
        if not self.url.strip():
            raise ValueError("source.url não pode ser vazia")
        if not self.license_name.strip() or not self.license_url.strip():
            raise ValueError("a licença da fonte deve ser informada")
        if SHA256_PATTERN.fullmatch(self.expected_sha256) is None:
            raise ValueError("source.expected_sha256 deve ter 64 dígitos hexadecimais")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "expected_sha256", self.expected_sha256.lower())


@dataclass(frozen=True)
class ClipConfig:
    output_yuv: Path
    provenance_path: Path
    width: int
    height: int
    fps_num: int
    fps_den: int
    start_frame: int
    frame_count: int
    pixel_format: str = "yuv420p"

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("clip.width e clip.height devem ser positivos")
        if self.width % 2 or self.height % 2:
            raise ValueError("YUV 4:2:0 exige largura e altura pares")
        if self.fps_num <= 0 or self.fps_den <= 0:
            raise ValueError("clip.fps_num e clip.fps_den devem ser positivos")
        if self.start_frame < 0:
            raise ValueError("clip.start_frame não pode ser negativo")
        if self.frame_count <= 0:
            raise ValueError("clip.frame_count deve ser positivo")
        if self.pixel_format != "yuv420p":
            raise ValueError("esta etapa exige clip.pixel_format=yuv420p")
        if self.output_yuv.suffix.lower() != ".yuv":
            raise ValueError("clip.output_yuv deve usar a extensão .yuv")
        if self.provenance_path.suffix.lower() != ".json":
            raise ValueError("clip.provenance_path deve usar a extensão .json")
        if self.output_yuv == self.provenance_path:
            raise ValueError("a saída YUV e a proveniência devem ser distintas")

    @property
    def end_frame(self) -> int:
        return self.start_frame + self.frame_count

    @property
    def frame_size_bytes(self) -> int:
        return self.width * self.height * 3 // 2

    @property
    def expected_output_size_bytes(self) -> int:
        return self.frame_size_bytes * self.frame_count

    @property
    def duration_s(self) -> float:
        return self.frame_count * self.fps_den / self.fps_num


@dataclass(frozen=True)
class SourcePreparationConfig:
    source_path: Path
    schema_version: int
    source: SourceArchiveConfig
    clip: ClipConfig
    ffmpeg_executable: str = "ffmpeg"

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"schema_version incompatível: esperado {SCHEMA_VERSION}"
            )
        if not self.ffmpeg_executable.strip():
            raise ValueError("ffmpeg_executable não pode ser vazio")
        paths = {
            self.source.input_xz,
            self.clip.output_yuv,
            self.clip.provenance_path,
        }
        if len(paths) != 3:
            raise ValueError("entrada, saída YUV e proveniência devem ser distintas")


@dataclass(frozen=True)
class Y4MHeader:
    raw: str
    width: int
    height: int
    fps_num: int
    fps_den: int
    interlace: str
    chroma: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _resolve(root: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def load_source_preparation_config(
    path: str | Path,
) -> SourcePreparationConfig:
    """Carrega uma configuração JSON e resolve seus caminhos relativos."""

    source_path = Path(path).resolve()
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    root = source_path.parent
    source_raw = raw["source"]
    clip_raw = raw["clip"]
    return SourcePreparationConfig(
        source_path=source_path,
        schema_version=int(raw.get("schema_version", 0)),
        source=SourceArchiveConfig(
            name=str(source_raw["name"]),
            url=str(source_raw["url"]),
            license_name=str(source_raw["license_name"]),
            license_url=str(source_raw["license_url"]),
            input_xz=_resolve(root, str(source_raw["input_xz"])),
            expected_sha256=str(source_raw["expected_sha256"]),
        ),
        clip=ClipConfig(
            output_yuv=_resolve(root, str(clip_raw["output_yuv"])),
            provenance_path=_resolve(root, str(clip_raw["provenance_path"])),
            width=int(clip_raw["width"]),
            height=int(clip_raw["height"]),
            fps_num=int(clip_raw["fps_num"]),
            fps_den=int(clip_raw.get("fps_den", 1)),
            start_frame=int(clip_raw["start_frame"]),
            frame_count=int(clip_raw["frame_count"]),
            pixel_format=str(clip_raw.get("pixel_format", "yuv420p")),
        ),
        ffmpeg_executable=str(raw.get("ffmpeg_executable", "ffmpeg")),
    )


def with_path_overrides(
    config: SourcePreparationConfig,
    *,
    input_xz: str | Path | None = None,
    output_yuv: str | Path | None = None,
    provenance_path: str | Path | None = None,
    ffmpeg_executable: str | None = None,
) -> SourcePreparationConfig:
    """Aplica caminhos locais sem alterar o arquivo de protocolo versionado."""

    source = SourceArchiveConfig(
        **{
            **asdict(config.source),
            "input_xz": (
                Path(input_xz).expanduser().resolve()
                if input_xz is not None
                else config.source.input_xz
            ),
        }
    )
    clip = ClipConfig(
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
    return SourcePreparationConfig(
        source_path=config.source_path,
        schema_version=config.schema_version,
        source=source,
        clip=clip,
        ffmpeg_executable=(
            ffmpeg_executable
            if ffmpeg_executable is not None
            else config.ffmpeg_executable
        ),
    )


def _parse_ratio(value: str, field: str) -> tuple[int, int]:
    try:
        numerator_text, denominator_text = value.split(":", maxsplit=1)
        numerator = int(numerator_text)
        denominator = int(denominator_text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} inválido no cabeçalho Y4M") from exc
    if numerator <= 0 or denominator <= 0:
        raise ValueError(f"{field} deve ser positivo no cabeçalho Y4M")
    return numerator, denominator


def parse_y4m_header(header: bytes) -> Y4MHeader:
    """Interpreta e valida o cabeçalho global de um fluxo YUV4MPEG2."""

    try:
        text = header.decode("ascii").rstrip("\r\n")
    except UnicodeDecodeError as exc:
        raise ValueError("o cabeçalho Y4M não é ASCII") from exc
    parts = text.split()
    if not parts or parts[0] != "YUV4MPEG2":
        raise ValueError("assinatura YUV4MPEG2 ausente")
    fields: dict[str, str] = {}
    for token in parts[1:]:
        if token and token[0] in {"W", "H", "F", "I", "C"}:
            fields[token[0]] = token[1:]
    try:
        width = int(fields["W"])
        height = int(fields["H"])
        interlace = fields["I"].lower()
        chroma = fields["C"].lower()
    except (KeyError, ValueError) as exc:
        raise ValueError("cabeçalho Y4M incompleto") from exc
    fps_num, fps_den = _parse_ratio(fields.get("F", ""), "framerate")
    if width <= 0 or height <= 0:
        raise ValueError("dimensões inválidas no cabeçalho Y4M")
    if interlace != "p":
        raise ValueError("a fonte Y4M deve ser progressiva")
    if chroma not in SUPPORTED_CHROMA:
        raise ValueError("a fonte Y4M deve usar YUV 4:2:0 de 8 bits")
    return Y4MHeader(
        raw=text,
        width=width,
        height=height,
        fps_num=fps_num,
        fps_den=fps_den,
        interlace=interlace,
        chroma=chroma,
    )


def _validate_header(header: Y4MHeader, clip: ClipConfig) -> None:
    actual = (header.width, header.height, header.fps_num, header.fps_den)
    expected = (clip.width, clip.height, clip.fps_num, clip.fps_den)
    if actual != expected:
        raise ValueError(
            "a geometria/frequência do Y4M difere da configuração: "
            f"detectado={actual}, esperado={expected}"
        )


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    config: SourcePreparationConfig,
    executable: str,
    destination: Path,
) -> list[str]:
    clip = config.clip
    return [
        executable,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-f",
        "yuv4mpegpipe",
        "-i",
        "pipe:0",
        "-map",
        "0:v:0",
        "-vf",
        (
            f"trim=start_frame={clip.start_frame}:end_frame={clip.end_frame},"
            "setpts=PTS-STARTPTS"
        ),
        "-frames:v",
        str(clip.frame_count),
        "-pix_fmt",
        clip.pixel_format,
        "-fps_mode",
        "passthrough",
        "-f",
        "rawvideo",
        str(destination),
    ]


def _stream_archive(
    archive: Path,
    command: Sequence[str],
    popen_factory: PopenFactory,
    clip: ClipConfig,
) -> Y4MHeader:
    process = popen_factory(
        list(command),
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if process.stdin is None or process.stderr is None:
        process.kill()
        process.wait()
        raise RuntimeError("não foi possível abrir os pipes do FFmpeg")
    header: bytes | None = None
    try:
        with lzma.open(archive, "rb") as source:
            header = source.readline()
            parsed = parse_y4m_header(header)
            _validate_header(parsed, clip)
            process.stdin.write(header)
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                if process.poll() is not None:
                    break
                process.stdin.write(chunk)
    except BrokenPipeError:
        # Esperado quando o FFmpeg conclui o último quadro e fecha pipe:0.
        pass
    except OSError as exc:
        if exc.errno not in {errno.EPIPE, errno.EINVAL}:
            if process.poll() is None:
                process.kill()
            process.wait()
            raise
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait()
        raise
    finally:
        try:
            process.stdin.close()
        except BrokenPipeError:
            pass
        except OSError as exc:
            if exc.errno not in {errno.EPIPE, errno.EINVAL}:
                raise
    stderr = process.stderr.read().decode("utf-8", errors="replace")
    returncode = process.wait()
    if returncode != 0:
        raise RuntimeError(
            f"FFmpeg falhou com código {returncode}: {stderr.strip()}"
        )
    assert header is not None
    return parsed


def _pipeline_metadata(module_path: Path) -> dict[str, object]:
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


def _normalized_config(config: SourcePreparationConfig) -> dict[str, object]:
    return {
        "schema_version": config.schema_version,
        "source": {
            **asdict(config.source),
            "input_xz": str(config.source.input_xz),
        },
        "clip": {
            **asdict(config.clip),
            "output_yuv": str(config.clip.output_yuv),
            "provenance_path": str(config.clip.provenance_path),
        },
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


def prepare_source(
    config: SourcePreparationConfig,
    *,
    overwrite: bool = False,
    popen_factory: PopenFactory = subprocess.Popen,
    runner: CommandRunner = subprocess.run,
    ffmpeg_info: dict[str, str] | None = None,
    progress: ProgressReporter | None = None,
) -> dict[str, object]:
    """Valida o XZ e extrai apenas o trecho normalizado para YUV bruto."""

    archive = config.source.input_xz
    clip = config.clip
    if not archive.is_file():
        raise FileNotFoundError(f"fonte Y4M/XZ não encontrada: {archive}")
    if not overwrite:
        for path in (clip.output_yuv, clip.provenance_path):
            if path.exists():
                raise FileExistsError(
                    f"arquivo já existe: {path}; use --overwrite conscientemente"
                )

    if progress is not None:
        progress("validando SHA-256 do arquivo Y4M/XZ")
    archive_hash = _sha256(archive)
    if archive_hash != config.source.expected_sha256:
        raise ValueError(
            "SHA-256 da fonte comprimida não confere: "
            f"detectado={archive_hash}, esperado={config.source.expected_sha256}"
        )

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
    command = build_ffmpeg_command(config, executable, temporary_output)
    if progress is not None:
        progress(
            f"extraindo quadros {clip.start_frame}..{clip.end_frame - 1} "
            "sem materializar o Y4M completo"
        )
    try:
        header = _stream_archive(archive, command, popen_factory, clip)
        actual_size = temporary_output.stat().st_size
        if actual_size != clip.expected_output_size_bytes:
            raise ValueError(
                "o tamanho do YUV normalizado é incompatível: "
                f"detectado={actual_size}, esperado={clip.expected_output_size_bytes}"
            )
        temporary_output.replace(clip.output_yuv)
    except BaseException:
        if temporary_output.is_file():
            temporary_output.unlink()
        raise

    output_hash = _sha256(clip.output_yuv)
    module_path = Path(__file__).resolve()
    payload: dict[str, object] = {
        "source_preparation_schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "configuration_file": str(config.source_path),
        "configuration_sha256": _sha256(config.source_path),
        "configuration": _normalized_config(config),
        "source_archive": {
            "path": str(archive),
            "url": config.source.url,
            "license_name": config.source.license_name,
            "license_url": config.source.license_url,
            "size_bytes": archive.stat().st_size,
            "sha256": archive_hash,
            "y4m_header": header.to_dict(),
        },
        "clip": {
            "path": str(clip.output_yuv),
            "start_frame": clip.start_frame,
            "end_frame_exclusive": clip.end_frame,
            "frame_count": clip.frame_count,
            "duration_s": clip.duration_s,
            "size_bytes": clip.output_yuv.stat().st_size,
            "sha256": output_hash,
            "pixel_format": clip.pixel_format,
        },
        "ffmpeg": tool,
        "ffmpeg_command": command,
        "pipeline": _pipeline_metadata(module_path),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
    }
    _write_json_atomic(clip.provenance_path, payload)
    return payload
