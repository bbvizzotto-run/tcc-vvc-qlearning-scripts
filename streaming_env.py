"""Ambiente determinístico para experimentos de streaming segmentado.

A implementação representa a transferência de segmentos pré-codificados. Nesta
primeira etapa, o tamanho de cada segmento é estimado pelo bitrate nominal. As
representações VVC reais serão conectadas ao mesmo ambiente posteriormente.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence


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
    ) -> None:
        if not bandwidth_trace_kbps:
            raise ValueError("o trace de largura de banda não pode ser vazio")
        if any(value <= 0 for value in bandwidth_trace_kbps):
            raise ValueError("todas as larguras de banda devem ser positivas")

        self.bandwidth_trace_kbps = tuple(float(v) for v in bandwidth_trace_kbps)
        self.config = config or StreamingConfig()
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

        # Se o próximo segmento não cabe, o player aguarda antes de requisitá-lo.
        wait_time_s = 0.0
        if self.playback_started:
            overflow_s = self.buffer_s + cfg.segment_duration_s - cfg.max_buffer_s
            if overflow_s > 0:
                wait_time_s = overflow_s
                self.buffer_s -= wait_time_s
                self.total_wait_time_s += wait_time_s

        segment_size_kbits = bitrate_kbps * cfg.segment_duration_s
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
            self.buffer_s + cfg.segment_duration_s,
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
        )
        self.results.append(result)
        self.segment_index += 1
        return result

    def summary(self) -> dict[str, float | int]:
        downloaded_video_s = len(self.results) * self.config.segment_duration_s
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
        }
