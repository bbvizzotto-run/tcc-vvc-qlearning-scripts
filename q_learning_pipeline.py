"""Integração do agente Q-Learning ao ambiente de streaming."""

from __future__ import annotations

import csv
import math
from bisect import bisect_right
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, pstdev
from typing import Sequence

from experiment import ExperimentConfig
from q_learning_agent import QLearningAgent
from segment_manifest import SegmentManifest
from streaming_env import SegmentResult, StreamingConfig, StreamingEnvironment
from trace_augmentation import TraceAugmentationConfig, augment_bandwidth_trace


@dataclass(frozen=True)
class RewardConfig:
    """Pesos explícitos da função de recompensa de QoE."""

    quality_weight: float = 1.0
    rebuffering_weight: float = 10.0
    switch_weight: float = 0.25
    low_buffer_weight: float = 1.0
    startup_weight: float = 0.0
    target_buffer_s: float = 8.0

    def __post_init__(self) -> None:
        weights = (
            self.quality_weight,
            self.rebuffering_weight,
            self.switch_weight,
            self.low_buffer_weight,
            self.startup_weight,
        )
        if any(weight < 0 for weight in weights):
            raise ValueError("os pesos da recompensa não podem ser negativos")
        if self.target_buffer_s <= 0:
            raise ValueError("target_buffer_s deve ser positivo")


@dataclass(frozen=True)
class TrainingConfig:
    episodes: int = 4000
    learning_rate: float = 0.1
    discount_factor: float = 0.95
    epsilon_start: float = 1.0
    epsilon_min: float = 0.05
    epsilon_decay: float = 0.995
    buffer_boundaries_s: tuple[float, ...] = (2.0, 4.0, 6.0, 8.0, 12.0, 16.0)
    seed: int = 42
    startup_guard: bool = False

    def __post_init__(self) -> None:
        if self.episodes <= 0:
            raise ValueError("episodes deve ser positivo")
        if self.seed < 0:
            raise ValueError("seed não pode ser negativa")
        if any(value < 0 for value in self.buffer_boundaries_s):
            raise ValueError("os limites do buffer não podem ser negativos")
        if tuple(sorted(set(self.buffer_boundaries_s))) != self.buffer_boundaries_s:
            raise ValueError("buffer_boundaries_s deve ser estritamente crescente")


@dataclass(frozen=True)
class QLearningDecision:
    state_index: int
    action_index: int
    action: str
    previous_bitrate_kbps: int
    bitrate_kbps: int
    forced_startup: bool = False


@dataclass(frozen=True)
class RewardBreakdown:
    reward: float
    quality_utility: float
    quality_term: float
    startup_penalty: float
    rebuffering_penalty: float
    switch_penalty: float
    low_buffer_penalty: float


class StateEncoder:
    """Codifica buffer, bitrate e throughput anterior em um índice tabular.

    A largura de banda do segmento atual nunca é usada antes da decisão. O
    último throughput observado possui ainda uma classe exclusiva para o estado
    desconhecido do primeiro segmento.
    """

    def __init__(
        self,
        bitrates_kbps: Sequence[int],
        buffer_boundaries_s: Sequence[float],
    ) -> None:
        bitrates = tuple(sorted(set(int(value) for value in bitrates_kbps)))
        boundaries = tuple(float(value) for value in buffer_boundaries_s)
        if not bitrates or any(value <= 0 for value in bitrates):
            raise ValueError("forneça ao menos um bitrate positivo")
        if tuple(sorted(set(boundaries))) != boundaries or any(
            value < 0 for value in boundaries
        ):
            raise ValueError("os limites do buffer devem ser crescentes e não negativos")

        self.bitrates_kbps = bitrates
        self.buffer_boundaries_s = boundaries
        self.num_buffer_states = len(boundaries) + 1
        self.num_bitrate_states = len(bitrates)
        # 0..M: quantidade de representações sustentáveis; M+1: desconhecido.
        self.num_throughput_states = len(bitrates) + 2
        self.unknown_throughput_state = len(bitrates) + 1
        self.num_states = (
            self.num_buffer_states
            * self.num_bitrate_states
            * self.num_throughput_states
        )

    def encode(
        self,
        buffer_s: float,
        current_bitrate_kbps: int,
        previous_throughput_kbps: float | None,
    ) -> int:
        if buffer_s < 0:
            raise ValueError("buffer_s não pode ser negativo")
        try:
            bitrate_state = self.bitrates_kbps.index(int(current_bitrate_kbps))
        except ValueError as exc:
            raise ValueError("bitrate atual não pertence à escada configurada") from exc

        buffer_state = bisect_right(self.buffer_boundaries_s, float(buffer_s))
        if previous_throughput_kbps is None:
            throughput_state = self.unknown_throughput_state
        else:
            if previous_throughput_kbps <= 0:
                raise ValueError("o throughput anterior deve ser positivo")
            throughput_state = bisect_right(
                self.bitrates_kbps,
                float(previous_throughput_kbps),
            )

        return (
            (buffer_state * self.num_bitrate_states + bitrate_state)
            * self.num_throughput_states
            + throughput_state
        )


class QLearningController:
    """Traduz as três ações tabulares em movimentos na escada de bitrate."""

    def __init__(self, agent: QLearningAgent, encoder: StateEncoder) -> None:
        if agent.state_space_size != encoder.num_states:
            raise ValueError("o agente e o codificador possuem espaços incompatíveis")
        if agent.action_space_size != 3:
            raise ValueError("o controlador requer três ações")
        self.agent = agent
        self.encoder = encoder
        self.reset()

    def reset(self) -> None:
        self.current_bitrate_index = 0
        self.previous_throughput_kbps: float | None = None

    @property
    def current_bitrate_kbps(self) -> int:
        return self.encoder.bitrates_kbps[self.current_bitrate_index]

    def current_state(self, buffer_s: float) -> int:
        return self.encoder.encode(
            buffer_s,
            self.current_bitrate_kbps,
            self.previous_throughput_kbps,
        )

    def select_bitrate(
        self,
        buffer_s: float,
        explore: bool,
        playback_started: bool = True,
        startup_guard: bool = False,
    ) -> QLearningDecision:
        state_index = self.current_state(buffer_s)
        forced_startup = startup_guard and not playback_started
        action_index = (
            0
            if forced_startup
            else self.agent.choose_action(state_index, explore=explore)
        )
        previous_bitrate = self.current_bitrate_kbps
        delta = (-1, 0, 1)[action_index]
        self.current_bitrate_index = min(
            len(self.encoder.bitrates_kbps) - 1,
            max(0, self.current_bitrate_index + delta),
        )
        return QLearningDecision(
            state_index=state_index,
            action_index=action_index,
            action=self.agent.get_action_meaning(action_index),
            previous_bitrate_kbps=previous_bitrate,
            bitrate_kbps=self.current_bitrate_kbps,
            forced_startup=forced_startup,
        )

    def observe_throughput(self, throughput_kbps: float) -> None:
        if throughput_kbps <= 0:
            raise ValueError("throughput_kbps deve ser positivo")
        self.previous_throughput_kbps = float(throughput_kbps)


def calculate_reward(
    result: SegmentResult,
    previous_bitrate_kbps: int,
    min_bitrate_kbps: int,
    max_bitrate_kbps: int,
    segment_duration_s: float,
    config: RewardConfig,
) -> RewardBreakdown:
    """Calcula utilidade de qualidade menos penalidades de QoE."""

    if max_bitrate_kbps == min_bitrate_kbps:
        quality_utility = 1.0
    else:
        quality_utility = math.log(
            result.bitrate_kbps / min_bitrate_kbps
        ) / math.log(max_bitrate_kbps / min_bitrate_kbps)

    quality_term = config.quality_weight * quality_utility
    startup_penalty = config.startup_weight * (
        result.startup_delay_s / segment_duration_s
    )
    rebuffering_penalty = config.rebuffering_weight * (
        result.rebuffering_s / segment_duration_s
    )
    switch_penalty = config.switch_weight * abs(
        math.log(result.bitrate_kbps / previous_bitrate_kbps)
    )
    low_buffer_ratio = max(
        0.0,
        config.target_buffer_s - result.buffer_after_s,
    ) / config.target_buffer_s
    low_buffer_penalty = config.low_buffer_weight * low_buffer_ratio
    reward = (
        quality_term
        - startup_penalty
        - rebuffering_penalty
        - switch_penalty
        - low_buffer_penalty
    )
    return RewardBreakdown(
        reward=reward,
        quality_utility=quality_utility,
        quality_term=quality_term,
        startup_penalty=startup_penalty,
        rebuffering_penalty=rebuffering_penalty,
        switch_penalty=switch_penalty,
        low_buffer_penalty=low_buffer_penalty,
    )


def _environment(
    trace: Sequence[float],
    config: ExperimentConfig,
    segment_manifest: SegmentManifest | None = None,
) -> StreamingEnvironment:
    return StreamingEnvironment(
        trace,
        StreamingConfig(
            segment_duration_s=config.segment_duration_s,
            startup_buffer_s=config.startup_buffer_s,
            max_buffer_s=config.max_buffer_s,
        ),
        segment_manifest=segment_manifest,
    )


def train_q_learning(
    named_traces: Sequence[tuple[str, Sequence[float]]],
    experiment_config: ExperimentConfig,
    training_config: TrainingConfig,
    reward_config: RewardConfig,
    trace_augmentation: TraceAugmentationConfig | None = None,
    segment_manifest: SegmentManifest | None = None,
) -> tuple[QLearningAgent, StateEncoder, list[dict[str, object]], dict[str, object]]:
    if not named_traces:
        raise ValueError("forneça ao menos um trace de treinamento")
    if any(not trace for _, trace in named_traces):
        raise ValueError("os traces de treinamento não podem ser vazios")
    if reward_config.target_buffer_s > experiment_config.max_buffer_s:
        raise ValueError("o buffer-alvo não pode exceder o buffer máximo")
    if (
        segment_manifest is not None
        and tuple(experiment_config.bitrates_kbps)
        != segment_manifest.bitrates_kbps
    ):
        raise ValueError(
            "a escada de bitrate da configuração difere do manifesto"
        )

    encoder = StateEncoder(
        experiment_config.bitrates_kbps,
        training_config.buffer_boundaries_s,
    )
    agent = QLearningAgent(
        state_space_size=encoder.num_states,
        action_space_size=3,
        learning_rate=training_config.learning_rate,
        discount_factor=training_config.discount_factor,
        epsilon=training_config.epsilon_start,
        epsilon_min=training_config.epsilon_min,
        epsilon_decay=training_config.epsilon_decay,
        seed=training_config.seed,
    )
    controller = QLearningController(agent, encoder)
    history: list[dict[str, object]] = []

    for episode in range(training_config.episodes):
        trace_name, base_trace = named_traces[episode % len(named_traces)]
        if trace_augmentation is None:
            trace = list(base_trace)
            augmented = False
        else:
            augmentation_seed = training_config.seed * 1_000_003 + episode
            trace = augment_bandwidth_trace(
                base_trace,
                trace_augmentation,
                augmentation_seed,
            )
            augmented = trace != list(base_trace)
        environment = _environment(trace, experiment_config, segment_manifest)
        controller.reset()
        total_reward = 0.0
        total_td_error = 0.0

        while not environment.done:
            decision = controller.select_bitrate(
                environment.buffer_s,
                explore=True,
                playback_started=environment.playback_started,
                startup_guard=training_config.startup_guard,
            )
            result = environment.step(decision.bitrate_kbps)
            controller.observe_throughput(result.bandwidth_kbps)
            reward = calculate_reward(
                result=result,
                previous_bitrate_kbps=decision.previous_bitrate_kbps,
                min_bitrate_kbps=encoder.bitrates_kbps[0],
                max_bitrate_kbps=encoder.bitrates_kbps[-1],
                segment_duration_s=result.segment_duration_s,
                config=reward_config,
            )
            next_state = controller.current_state(environment.buffer_s)
            td_error = agent.update_q_table(
                current_state_index=decision.state_index,
                action=decision.action_index,
                reward=reward.reward,
                next_state_index=next_state,
                terminal=environment.done,
            )
            total_reward += reward.reward
            total_td_error += abs(td_error)

        episode_summary = environment.summary()
        history.append(
            {
                "episode": episode,
                "trace": trace_name,
                "augmented": augmented,
                "bandwidth_mean_kbps": fmean(trace),
                "bandwidth_min_kbps": min(trace),
                "epsilon": agent.epsilon,
                "total_reward": total_reward,
                "mean_reward": total_reward / len(environment.results),
                "mean_abs_td_error": total_td_error / len(environment.results),
                "average_bitrate_kbps": fmean(
                    result.bitrate_kbps for result in environment.results
                ),
                "rebuffering_s": episode_summary["rebuffering_s"],
                "buffer_std_s": pstdev(
                    result.buffer_after_s for result in environment.results
                ),
            }
        )
        agent.decay_epsilon()

    metadata: dict[str, object] = {
        "format_version": 2,
        "bitrates_kbps": list(encoder.bitrates_kbps),
        "buffer_boundaries_s": list(encoder.buffer_boundaries_s),
        "experiment_config": asdict(experiment_config),
        "training_config": asdict(training_config),
        "reward_config": asdict(reward_config),
        "training_traces": [name for name, _ in named_traces],
        "trace_augmentation": (
            asdict(trace_augmentation) if trace_augmentation is not None else None
        ),
        "segment_manifest": (
            segment_manifest.metadata()
            if segment_manifest is not None
            else None
        ),
    }
    return agent, encoder, history, metadata


def run_q_learning_experiment(
    bandwidth_trace_kbps: Sequence[float],
    experiment_config: ExperimentConfig,
    agent: QLearningAgent,
    encoder: StateEncoder,
    reward_config: RewardConfig,
    segments: int | None = None,
    segment_manifest: SegmentManifest | None = None,
    startup_guard: bool = False,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    trace = list(bandwidth_trace_kbps)
    if segments is not None:
        if segments <= 0:
            raise ValueError("segments deve ser positivo")
        if segments > len(trace):
            raise ValueError("segments excede o número de amostras do trace")
        trace = trace[:segments]
    if tuple(experiment_config.bitrates_kbps) != encoder.bitrates_kbps:
        raise ValueError("a escada de bitrate não corresponde ao modelo")
    if (
        segment_manifest is not None
        and encoder.bitrates_kbps != segment_manifest.bitrates_kbps
    ):
        raise ValueError("a escada de bitrate do modelo difere do manifesto")

    environment = _environment(trace, experiment_config, segment_manifest)
    controller = QLearningController(agent, encoder)
    rows: list[dict[str, object]] = []
    total_reward = 0.0

    while not environment.done:
        decision = controller.select_bitrate(
            environment.buffer_s,
            explore=False,
            playback_started=environment.playback_started,
            startup_guard=startup_guard,
        )
        result = environment.step(decision.bitrate_kbps)
        controller.observe_throughput(result.bandwidth_kbps)
        reward = calculate_reward(
            result=result,
            previous_bitrate_kbps=decision.previous_bitrate_kbps,
            min_bitrate_kbps=encoder.bitrates_kbps[0],
            max_bitrate_kbps=encoder.bitrates_kbps[-1],
            segment_duration_s=result.segment_duration_s,
            config=reward_config,
        )
        total_reward += reward.reward
        row = result.to_dict()
        row.update(
            {
                "state_index": decision.state_index,
                "action_index": decision.action_index,
                "action": decision.action,
                "forced_startup": decision.forced_startup,
                **asdict(reward),
            }
        )
        rows.append(row)

    summary: dict[str, object] = environment.summary()
    bitrates = [float(row["bitrate_kbps"]) for row in rows]
    buffers = [float(row["buffer_after_s"]) for row in rows]
    video_duration_s = float(summary["video_duration_s"])
    payload_kbits = sum(float(row["segment_size_kbits"]) for row in rows)
    summary.update(
        {
            "controller": "q-learning",
            "seed": experiment_config.seed,
            "total_reward": total_reward,
            "mean_reward": total_reward / len(rows),
            "average_bitrate_kbps": fmean(bitrates),
            "average_payload_bitrate_kbps": payload_kbits / video_duration_s,
            "buffer_mean_s": fmean(buffers),
            "buffer_std_s": pstdev(buffers),
            "startup_guard": startup_guard,
            "configuration": asdict(experiment_config),
            "segment_manifest": (
                segment_manifest.metadata()
                if segment_manifest is not None
                else None
            ),
        }
    )
    return rows, summary


def save_training_history(
    history: Sequence[dict[str, object]],
    output_csv: str | Path,
) -> Path:
    if not history:
        raise ValueError("não há histórico de treinamento")
    destination = Path(output_csv)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(history[0].keys()),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(history)
    return destination


def components_from_model(
    model_path: str | Path,
    seed: int,
) -> tuple[
    QLearningAgent,
    StateEncoder,
    ExperimentConfig,
    RewardConfig,
    dict[str, object],
]:
    agent, metadata = QLearningAgent.load(model_path, seed=seed)
    try:
        raw_experiment = dict(metadata["experiment_config"])
        raw_reward = dict(metadata["reward_config"])
        bitrates = tuple(int(value) for value in metadata["bitrates_kbps"])
        boundaries = tuple(float(value) for value in metadata["buffer_boundaries_s"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("metadados incompletos ou inválidos no modelo") from exc

    raw_experiment["bitrates_kbps"] = tuple(raw_experiment["bitrates_kbps"])
    raw_experiment["seed"] = seed
    experiment_config = ExperimentConfig(**raw_experiment)
    reward_config = RewardConfig(**raw_reward)
    encoder = StateEncoder(bitrates, boundaries)
    if agent.state_space_size != encoder.num_states or agent.action_space_size != 3:
        raise ValueError("dimensões do modelo incompatíveis com seus metadados")
    return agent, encoder, experiment_config, reward_config, metadata
