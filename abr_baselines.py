"""Baselines ABR competitivos para comparação com o Q-Learning.

As decisões usam somente o buffer atual, o manifesto público e medições de
throughput de segmentos já concluídos. A banda do segmento corrente nunca é
consultada antes da escolha da representação.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from statistics import harmonic_mean
from typing import Sequence

from controllers import ControllerDecision
from q_learning_pipeline import RewardConfig, calculate_reward
from segment_manifest import SegmentManifest
from streaming_env import SegmentResult, StreamingConfig


@dataclass(frozen=True)
class ThroughputConfig:
    """Parâmetros congelados do baseline baseado em throughput."""

    history_window: int = 5
    safety_factor: float = 0.85

    def __post_init__(self) -> None:
        if self.history_window <= 0:
            raise ValueError("history_window deve ser positivo")
        if not 0 < self.safety_factor <= 1:
            raise ValueError("safety_factor deve pertencer a (0, 1]")


@dataclass(frozen=True)
class BolaConfig:
    """Parâmetros congelados do BOLA-BASIC."""

    minimum_buffer_s: float = 10.0
    buffer_target_s: float = 20.0

    def __post_init__(self) -> None:
        if self.minimum_buffer_s <= 0:
            raise ValueError("minimum_buffer_s deve ser positivo")
        if self.buffer_target_s <= self.minimum_buffer_s:
            raise ValueError("buffer_target_s deve exceder minimum_buffer_s")


@dataclass(frozen=True)
class RobustMpcConfig:
    """Parâmetros congelados do RobustMPC."""

    horizon: int = 5
    history_window: int = 5
    error_window: int = 5

    def __post_init__(self) -> None:
        if self.horizon <= 0:
            raise ValueError("horizon deve ser positivo")
        if self.history_window <= 0:
            raise ValueError("history_window deve ser positivo")
        if self.error_window <= 0:
            raise ValueError("error_window deve ser positivo")


def _bitrates(values: Sequence[int]) -> tuple[int, ...]:
    bitrates = tuple(sorted(set(int(value) for value in values)))
    if not bitrates or any(value <= 0 for value in bitrates):
        raise ValueError("forneça ao menos um bitrate positivo")
    return bitrates


def _action(previous_index: int, current_index: int) -> str:
    if current_index < previous_index:
        return "decrease"
    if current_index > previous_index:
        return "increase"
    return "maintain"


def _observed_throughput(result: SegmentResult) -> float:
    if result.download_time_s <= 0:
        raise ValueError("download_time_s deve ser positivo")
    return result.segment_size_kbits / result.download_time_s


class ThroughputController:
    """Seleciona o maior bitrate sustentável por uma média harmônica segura."""

    def __init__(
        self,
        bitrates_kbps: Sequence[int],
        config: ThroughputConfig | None = None,
    ) -> None:
        self.bitrates_kbps = _bitrates(bitrates_kbps)
        self.config = config or ThroughputConfig()
        self.reset()

    def reset(self) -> None:
        self.current_index = 0
        self.throughput_history_kbps: list[float] = []

    @property
    def estimated_throughput_kbps(self) -> float | None:
        if not self.throughput_history_kbps:
            return None
        return harmonic_mean(self.throughput_history_kbps)

    def select_bitrate(self) -> ControllerDecision:
        previous_index = self.current_index
        estimate = self.estimated_throughput_kbps
        if estimate is None:
            self.current_index = 0
        else:
            safe_throughput = self.config.safety_factor * estimate
            sustainable = [
                index
                for index, bitrate in enumerate(self.bitrates_kbps)
                if bitrate <= safe_throughput
            ]
            self.current_index = sustainable[-1] if sustainable else 0
        return ControllerDecision(
            bitrate_kbps=self.bitrates_kbps[self.current_index],
            action=_action(previous_index, self.current_index),
        )

    def observe(self, result: SegmentResult) -> None:
        self.throughput_history_kbps.append(_observed_throughput(result))
        del self.throughput_history_kbps[: -self.config.history_window]


class BolaController:
    """Implementa o núcleo buffer-only do BOLA-BASIC.

    A utilidade é logarítmica e normalizada para começar em 1, seguindo a
    parametrização publicada e usada pela implementação de referência.
    """

    def __init__(
        self,
        bitrates_kbps: Sequence[int],
        config: BolaConfig | None = None,
    ) -> None:
        self.bitrates_kbps = _bitrates(bitrates_kbps)
        self.config = config or BolaConfig()
        minimum = self.bitrates_kbps[0]
        self.utilities = tuple(
            math.log(bitrate / minimum) + 1.0
            for bitrate in self.bitrates_kbps
        )
        if len(self.bitrates_kbps) == 1:
            self.gp = 1.0
            self.vp = self.config.minimum_buffer_s
        else:
            self.gp = (self.utilities[-1] - 1.0) / (
                self.config.buffer_target_s / self.config.minimum_buffer_s - 1.0
            )
            self.vp = self.config.minimum_buffer_s / self.gp
        self.reset()

    def reset(self) -> None:
        self.current_index = 0

    def select_bitrate(self, buffer_s: float) -> ControllerDecision:
        if buffer_s < 0:
            raise ValueError("buffer_s não pode ser negativo")
        previous_index = self.current_index
        scores = [
            (
                self.vp * (utility - 1.0 + self.gp) - buffer_s
            ) / bitrate
            for bitrate, utility in zip(self.bitrates_kbps, self.utilities)
        ]
        # O primeiro máximo preserva a escolha conservadora em empates.
        self.current_index = max(range(len(scores)), key=scores.__getitem__)
        return ControllerDecision(
            bitrate_kbps=self.bitrates_kbps[self.current_index],
            action=_action(previous_index, self.current_index),
        )


class RobustMpcController:
    """RobustMPC com horizonte finito e correção pelo pior erro recente."""

    def __init__(
        self,
        bitrates_kbps: Sequence[int],
        streaming_config: StreamingConfig,
        reward_config: RewardConfig,
        segment_manifest: SegmentManifest | None = None,
        config: RobustMpcConfig | None = None,
    ) -> None:
        self.bitrates_kbps = _bitrates(bitrates_kbps)
        self.streaming_config = streaming_config
        self.reward_config = reward_config
        self.segment_manifest = segment_manifest
        self.config = config or RobustMpcConfig()
        if (
            segment_manifest is not None
            and segment_manifest.bitrates_kbps != self.bitrates_kbps
        ):
            raise ValueError("a escada de bitrate difere do manifesto")
        self.reset()

    def reset(self) -> None:
        self.current_index = 0
        self.throughput_history_kbps: list[float] = []
        self.prediction_errors: list[float] = []
        self.last_prediction_kbps: float | None = None

    @property
    def predicted_throughput_kbps(self) -> float | None:
        if not self.throughput_history_kbps:
            return None
        estimate = harmonic_mean(self.throughput_history_kbps)
        worst_error = max(self.prediction_errors, default=0.0)
        return estimate / (1.0 + worst_error)

    def _segment_data(self, segment: int, bitrate: int) -> tuple[float, float]:
        if self.segment_manifest is None:
            duration = self.streaming_config.segment_duration_s
            return duration, bitrate * duration
        metadata = self.segment_manifest.get(segment, bitrate)
        return metadata.duration_s, metadata.size_kbits

    def _sequence_reward(
        self,
        sequence: Sequence[int],
        segment_index: int,
        buffer_s: float,
        playback_started: bool,
        predicted_throughput_kbps: float,
    ) -> float:
        previous_bitrate = self.bitrates_kbps[self.current_index]
        total_reward = 0.0
        simulated_buffer = float(buffer_s)
        simulated_started = bool(playback_started)

        for offset, bitrate in enumerate(sequence):
            duration, size_kbits = self._segment_data(
                segment_index + offset,
                bitrate,
            )
            if simulated_started:
                overflow = (
                    simulated_buffer
                    + duration
                    - self.streaming_config.max_buffer_s
                )
                if overflow > 0:
                    simulated_buffer -= overflow
            download_time = size_kbits / predicted_throughput_kbps
            rebuffering = 0.0
            if simulated_started:
                rebuffering = max(0.0, download_time - simulated_buffer)
                simulated_buffer = max(0.0, simulated_buffer - download_time)
            simulated_buffer = min(
                simulated_buffer + duration,
                self.streaming_config.max_buffer_s,
            )
            if (
                not simulated_started
                and simulated_buffer >= self.streaming_config.startup_buffer_s
            ):
                simulated_started = True

            forecast = SegmentResult(
                segment=segment_index + offset,
                bitrate_kbps=bitrate,
                bandwidth_kbps=predicted_throughput_kbps,
                segment_size_kbits=size_kbits,
                download_time_s=download_time,
                startup_delay_s=0.0,
                wait_time_s=0.0,
                buffer_before_s=0.0,
                buffer_after_s=simulated_buffer,
                rebuffering_s=rebuffering,
                playback_started=simulated_started,
                segment_duration_s=duration,
            )
            total_reward += calculate_reward(
                result=forecast,
                previous_bitrate_kbps=previous_bitrate,
                min_bitrate_kbps=self.bitrates_kbps[0],
                max_bitrate_kbps=self.bitrates_kbps[-1],
                segment_duration_s=duration,
                config=self.reward_config,
            ).reward
            previous_bitrate = bitrate
        return total_reward

    def select_bitrate(
        self,
        buffer_s: float,
        segment_index: int,
        playback_started: bool,
        remaining_segments: int,
    ) -> ControllerDecision:
        if buffer_s < 0:
            raise ValueError("buffer_s não pode ser negativo")
        if segment_index < 0 or remaining_segments <= 0:
            raise ValueError("posição do segmento inválida")
        previous_index = self.current_index
        prediction = self.predicted_throughput_kbps
        self.last_prediction_kbps = prediction
        if prediction is None:
            self.current_index = 0
        else:
            horizon = min(self.config.horizon, remaining_segments)
            if self.segment_manifest is not None:
                horizon = min(
                    horizon,
                    self.segment_manifest.segment_count - segment_index,
                )
            best_sequence: tuple[int, ...] | None = None
            best_reward = -math.inf
            for sequence in itertools.product(
                self.bitrates_kbps,
                repeat=horizon,
            ):
                reward = self._sequence_reward(
                    sequence,
                    segment_index,
                    buffer_s,
                    playback_started,
                    prediction,
                )
                if reward > best_reward:
                    best_reward = reward
                    best_sequence = sequence
            assert best_sequence is not None
            self.current_index = self.bitrates_kbps.index(best_sequence[0])
        return ControllerDecision(
            bitrate_kbps=self.bitrates_kbps[self.current_index],
            action=_action(previous_index, self.current_index),
        )

    def observe(self, result: SegmentResult) -> None:
        actual = _observed_throughput(result)
        if self.last_prediction_kbps is not None:
            error = abs(self.last_prediction_kbps - actual) / actual
            self.prediction_errors.append(error)
            del self.prediction_errors[: -self.config.error_window]
        self.throughput_history_kbps.append(actual)
        del self.throughput_history_kbps[: -self.config.history_window]
