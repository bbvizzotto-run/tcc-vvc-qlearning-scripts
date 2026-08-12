"""Ambiente determinístico para streaming com tamanhos nominais ou medidos."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

from segment_manifest import SegmentManifest


@dataclass(frozen=True)
class StreamingConfig:
    """Parâmetros temporais e limites do player simulado."""

    segment_duration_s: float = 2.0
    startup_buffer_s: float = 4.0
    max_buffer_s: float = 20.0

    def __post_init__(self) -> None:
        if self.segment_duration_s <= 0:
            raise ValueError("segment_duration_s deve ser positivo")
        if self.startup_buffer_s <= 0:
            raise ValueError("startup_buffer_s deve ser positivo")
        if self.max_buffer_s < self.startup_buffer_s:
            raise ValueError("max_buffer_s deve ser >= startup_buffer_s")
        if self.segment_duration_s > self.max_buffer_s:
            raise ValueError("um segmento deve caber no buffer")


@dataclass(frozen=True)
class SegmentResult:
    """Observações registradas durante a transferência de um segmento."""

    segment: int
    bitrate_kbps: int
    bandwidth_kbps: float
    segment_size_kbits: float
    download_time_s: float
    startup_delay_s: float
    wait_time_s: float
    buffer_before_s: float
    buffer_after_s: float
    rebuffering_s: float
    playback_started: bool
    segment_duration_s: float = 2.0
    segment_size_source: str = "nominal"
    manifest_sequence: str | None = None
    psnr_y_db: float | None = None
    source_file: str | None = None
    sha256: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class StreamingEnvironment:
    """Simula buffer e download usando uma largura de banda por segmento.

    O trace é consumido em ordem. Antes do início da reprodução, os downloads
    contam como atraso inicial, sem rebuffering. Depois do início, o download
    consome o buffer e qualquer excedente é contabilizado como interrupção.
    """

    def __init__(
        self,
        bandwidth_trace_kbps: Sequence[float],
        config: StreamingConfig | None = None,
        segment_manifest: SegmentManifest | None = None,
    ) -> None:
        if not bandwidth_trace_kbps:
            raise ValueError("o trace de largura de banda não pode ser vazio")
        if any(value <= 0 for value in bandwidth_trace_kbps):
            raise ValueError("todas as larguras de banda devem ser positivas")

        self.bandwidth_trace_kbps = tuple(float(v) for v in bandwidth_trace_kbps)
        self.config = config or StreamingConfig()
        self.segment_manifest = segment_manifest
        if (
            segment_manifest is not None
            and len(self.bandwidth_trace_kbps) > segment_manifest.segment_count
        ):
            raise ValueError(
                "o trace de banda contém mais segmentos que o manifesto"
            )
        if segment_manifest is not None:
            for segment in range(len(self.bandwidth_trace_kbps)):
                duration = segment_manifest.get(
                    segment,
                    segment_manifest.bitrates_kbps[0],
                ).duration_s
                if duration > self.config.max_buffer_s:
                    raise ValueError(
                        f"o segmento {segment} não cabe no buffer configurado"
                    )
        self.reset()

    def reset(self) -> None:
        self.segment_index = 0
        self.buffer_s = 0.0
        self.playback_started = False
        self.total_startup_delay_s = 0.0
        self.total_rebuffering_s = 0.0
        self.total_wait_time_s = 0.0
        self.results: list[SegmentResult] = []

    @property
    def done(self) -> bool:
        return self.segment_index >= len(self.bandwidth_trace_kbps)

    def step(self, bitrate_kbps: int) -> SegmentResult:
        if self.done:
            raise RuntimeError("o trace terminou; chame reset() para nova execução")
        if bitrate_kbps <= 0:
            raise ValueError("bitrate_kbps deve ser positivo")

        cfg = self.config
        bandwidth_kbps = self.bandwidth_trace_kbps[self.segment_index]
        buffer_before_s = self.buffer_s

        if self.segment_manifest is None:
            segment_duration_s = cfg.segment_duration_s
            segment_size_kbits = bitrate_kbps * segment_duration_s
            segment_size_source = "nominal"
            manifest_sequence = None
            psnr_y_db = None
            source_file = None
            sha256 = None
        else:
            metadata = self.segment_manifest.get(
                self.segment_index,
                bitrate_kbps,
            )
            segment_duration_s = metadata.duration_s
            segment_size_kbits = metadata.size_kbits
            segment_size_source = "manifest"
            manifest_sequence = metadata.sequence
            psnr_y_db = metadata.psnr_y_db
            source_file = metadata.source_file
            sha256 = metadata.sha256

        # Se o próximo segmento não cabe, o player aguarda antes de requisitá-lo.
        wait_time_s = 0.0
        if self.playback_started:
            overflow_s = self.buffer_s + segment_duration_s - cfg.max_buffer_s
            if overflow_s > 0:
                wait_time_s = overflow_s
                self.buffer_s -= wait_time_s
                self.total_wait_time_s += wait_time_s

        download_time_s = segment_size_kbits / bandwidth_kbps
        startup_delay_s = 0.0
        rebuffering_s = 0.0

        if self.playback_started:
            if download_time_s <= self.buffer_s:
                self.buffer_s -= download_time_s
            else:
                rebuffering_s = download_time_s - self.buffer_s
                self.buffer_s = 0.0
                self.total_rebuffering_s += rebuffering_s
        else:
            startup_delay_s = download_time_s
            self.total_startup_delay_s += startup_delay_s

        self.buffer_s = min(
            self.buffer_s + segment_duration_s,
            cfg.max_buffer_s,
        )
        if not self.playback_started and self.buffer_s >= cfg.startup_buffer_s:
            self.playback_started = True

        result = SegmentResult(
            segment=self.segment_index,
            bitrate_kbps=bitrate_kbps,
            bandwidth_kbps=bandwidth_kbps,
            segment_size_kbits=segment_size_kbits,
            download_time_s=download_time_s,
            startup_delay_s=startup_delay_s,
            wait_time_s=wait_time_s,
            buffer_before_s=buffer_before_s,
            buffer_after_s=self.buffer_s,
            rebuffering_s=rebuffering_s,
            playback_started=self.playback_started,
            segment_duration_s=segment_duration_s,
            segment_size_source=segment_size_source,
            manifest_sequence=manifest_sequence,
            psnr_y_db=psnr_y_db,
            source_file=source_file,
            sha256=sha256,
        )
        self.results.append(result)
        self.segment_index += 1
        return result

    def summary(self) -> dict[str, object]:
        downloaded_video_s = sum(
            result.segment_duration_s for result in self.results
        )
        return {
            "segments": len(self.results),
            "video_duration_s": downloaded_video_s,
            "startup_delay_s": self.total_startup_delay_s,
            "rebuffering_s": self.total_rebuffering_s,
            "rebuffering_rate_percent": (
                100.0 * self.total_rebuffering_s / downloaded_video_s
                if downloaded_video_s
                else 0.0
            ),
            "wait_time_s": self.total_wait_time_s,
            "segment_size_source": (
                "manifest" if self.segment_manifest is not None else "nominal"
            ),
            "manifest_sequence": (
                self.segment_manifest.sequence
                if self.segment_manifest is not None
                else None
            ),
        }
