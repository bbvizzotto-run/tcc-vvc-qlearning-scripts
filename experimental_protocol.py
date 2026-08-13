"""Protocolo multi-semente com intervalos de confiança e análise pareada."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from statistics import fmean, stdev
from typing import Any, Mapping, Sequence

from experiment import ExperimentConfig, load_bandwidth_trace, run_static_experiment
from q_learning_agent import QLearningAgent
from q_learning_pipeline import (
    RewardConfig,
    StateEncoder,
    TrainingConfig,
    run_q_learning_experiment,
    train_q_learning,
)
from segment_manifest import load_segment_manifest
from trace_augmentation import TraceAugmentationConfig


METRICS: tuple[str, ...] = (
    "startup_delay_s",
    "rebuffering_s",
    "rebuffering_rate_percent",
    "average_bitrate_kbps",
    "buffer_mean_s",
    "buffer_std_s",
)
MANIFEST_METRICS: tuple[str, ...] = ("average_payload_bitrate_kbps",)

BETTER_WHEN: Mapping[str, str] = {
    "startup_delay_s": "lower",
    "rebuffering_s": "lower",
    "rebuffering_rate_percent": "lower",
    "average_bitrate_kbps": "higher",
    "average_payload_bitrate_kbps": "higher",
    "buffer_mean_s": "descriptive",
    "buffer_std_s": "lower",
}

# Valores críticos bilaterais para IC95%, indexados pelos graus de liberdade.
T_CRITICAL_95: tuple[float | None, ...] = (
    None,
    12.706,
    4.303,
    3.182,
    2.776,
    2.571,
    2.447,
    2.365,
    2.306,
    2.262,
    2.228,
    2.201,
    2.179,
    2.160,
    2.145,
    2.131,
    2.120,
    2.110,
    2.101,
    2.093,
    2.086,
    2.080,
    2.074,
    2.069,
    2.064,
    2.060,
    2.056,
    2.052,
    2.048,
    2.045,
    2.042,
)


@dataclass(frozen=True)
class ProtocolDefinition:
    source_path: Path
    protocol_version: int
    confidence_level: float
    seeds: tuple[int, ...]
    training_trace_paths: tuple[Path, ...]
    evaluation_trace_paths: tuple[Path, ...]
    experiment_config: ExperimentConfig
    training_config: TrainingConfig
    reward_config: RewardConfig
    trace_augmentation: TraceAugmentationConfig | None = None
    segment_manifest_path: Path | None = None
    training_trace_scales: tuple[float, ...] = ()
    evaluation_trace_scales: tuple[float, ...] = ()


@dataclass
class ProtocolResult:
    raw_runs: list[dict[str, object]]
    aggregate: list[dict[str, object]]
    paired_differences: list[dict[str, object]]
    training_summary: list[dict[str, object]]
    metrics: tuple[str, ...]
    models: dict[int, tuple[QLearningAgent, dict[str, object]]] = field(
        repr=False
    )


def confidence_interval_95(values: Sequence[float]) -> dict[str, float | int]:
    """Calcula IC95% bilateral da média usando t de Student."""

    numeric = [float(value) for value in values]
    if len(numeric) < 2:
        raise ValueError("o intervalo de confiança requer ao menos duas observações")
    n = len(numeric)
    mean = fmean(numeric)
    sample_std = stdev(numeric)
    degrees_of_freedom = n - 1
    critical = (
        T_CRITICAL_95[degrees_of_freedom]
        if degrees_of_freedom < len(T_CRITICAL_95)
        else 1.96
    )
    assert critical is not None
    half_width = critical * sample_std / math.sqrt(n)
    return {
        "n": n,
        "mean": mean,
        "std": sample_std,
        "ci95_half_width": half_width,
        "ci95_low": mean - half_width,
        "ci95_high": mean + half_width,
    }


def load_protocol_definition(path: str | Path) -> ProtocolDefinition:
    source_path = Path(path).resolve()
    with source_path.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    seeds = tuple(int(value) for value in raw["seeds"])
    if len(seeds) < 2 or len(set(seeds)) != len(seeds):
        raise ValueError("o protocolo requer ao menos duas sementes distintas")
    if any(seed < 0 for seed in seeds):
        raise ValueError("as sementes não podem ser negativas")
    confidence_level = float(raw.get("confidence_level", 0.95))
    if confidence_level != 0.95:
        raise ValueError("esta versão implementa somente IC95%")

    root = source_path.parent

    def resolve_traces(
        items: Sequence[str | Mapping[str, Any]],
    ) -> tuple[tuple[Path, ...], tuple[float, ...]]:
        paths: list[Path] = []
        scales: list[float] = []
        for item in items:
            if isinstance(item, str):
                trace_path = item
                scale = 1.0
            elif isinstance(item, Mapping):
                trace_path = str(item["path"])
                scale = float(item.get("bandwidth_scale", 1.0))
            else:
                raise ValueError("cada trace deve ser um caminho ou objeto")
            if not math.isfinite(scale) or scale <= 0:
                raise ValueError("bandwidth_scale deve ser positivo e finito")
            paths.append((root / trace_path).resolve())
            scales.append(scale)
        paths_tuple = tuple(paths)
        if not paths_tuple or any(not item.is_file() for item in paths_tuple):
            raise ValueError("um ou mais traces do protocolo não existem")
        return paths_tuple, tuple(scales)

    training_trace_paths, training_trace_scales = resolve_traces(
        raw["training_traces"]
    )
    evaluation_trace_paths, evaluation_trace_scales = resolve_traces(
        raw["evaluation_traces"]
    )

    experiment_raw = dict(raw["experiment_config"])
    experiment_raw["bitrates_kbps"] = tuple(experiment_raw["bitrates_kbps"])
    experiment_raw["seed"] = seeds[0]
    training_raw = dict(raw["training_config"])
    training_raw["buffer_boundaries_s"] = tuple(
        training_raw["buffer_boundaries_s"]
    )
    training_raw["seed"] = seeds[0]
    segment_manifest_path = (
        (root / raw["segment_manifest"]).resolve()
        if raw.get("segment_manifest") is not None
        else None
    )
    if segment_manifest_path is not None and not segment_manifest_path.is_file():
        raise ValueError("o manifesto de segmentos do protocolo não existe")

    return ProtocolDefinition(
        source_path=source_path,
        protocol_version=int(raw["protocol_version"]),
        confidence_level=confidence_level,
        seeds=seeds,
        training_trace_paths=training_trace_paths,
        evaluation_trace_paths=evaluation_trace_paths,
        experiment_config=ExperimentConfig(**experiment_raw),
        training_config=TrainingConfig(**training_raw),
        reward_config=RewardConfig(**raw["reward_config"]),
        trace_augmentation=(
            TraceAugmentationConfig(**raw["trace_augmentation"])
            if raw.get("trace_augmentation") is not None
            else None
        ),
        segment_manifest_path=segment_manifest_path,
        training_trace_scales=training_trace_scales,
        evaluation_trace_scales=evaluation_trace_scales,
    )


def clone_agent(agent: QLearningAgent, seed: int) -> QLearningAgent:
    clone = QLearningAgent(
        state_space_size=agent.state_space_size,
        action_space_size=agent.action_space_size,
        learning_rate=agent.learning_rate,
        discount_factor=agent.discount_factor,
        epsilon=agent.epsilon,
        epsilon_min=agent.epsilon_min,
        epsilon_decay=agent.epsilon_decay,
        seed=seed,
    )
    clone.q_table = agent.q_table.copy()
    return clone


def _aggregate(
    raw_runs: Sequence[dict[str, object]],
    seeds: Sequence[int],
    evaluation_trace_names: Sequence[str],
    metrics: Sequence[str] = METRICS,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    controllers = ("static", "q-learning")

    for trace in evaluation_trace_names:
        for controller in controllers:
            selected = [
                row
                for row in raw_runs
                if row["trace"] == trace and row["controller"] == controller
            ]
            for metric in metrics:
                stats = confidence_interval_95(
                    [float(row[metric]) for row in selected]
                )
                rows.append(
                    {
                        "scope": "per_trace",
                        "trace": trace,
                        "controller": controller,
                        "metric": metric,
                        "better_when": BETTER_WHEN[metric],
                        **stats,
                    }
                )

    # Cada semente contribui com uma observação: a média dos traces daquela
    # semente. Isso evita inflar n tratando traces repetidos como independentes.
    for controller in controllers:
        for metric in metrics:
            per_seed_means = []
            for seed in seeds:
                selected = [
                    float(row[metric])
                    for row in raw_runs
                    if row["training_seed"] == seed
                    and row["controller"] == controller
                ]
                per_seed_means.append(fmean(selected))
            stats = confidence_interval_95(per_seed_means)
            rows.append(
                {
                    "scope": "overall_per_seed",
                    "trace": "all_evaluation_traces",
                    "controller": controller,
                    "metric": metric,
                    "better_when": BETTER_WHEN[metric],
                    **stats,
                }
            )
    return rows


def _paired_differences(
    raw_runs: Sequence[dict[str, object]],
    seeds: Sequence[int],
    evaluation_trace_names: Sequence[str],
    metrics: Sequence[str] = METRICS,
) -> list[dict[str, object]]:
    paired_by_seed_trace: dict[tuple[int, str], dict[str, dict[str, object]]] = {}
    for row in raw_runs:
        key = (int(row["training_seed"]), str(row["trace"]))
        paired_by_seed_trace.setdefault(key, {})[str(row["controller"])] = row

    rows: list[dict[str, object]] = []
    deltas: dict[tuple[int, str, str], float] = {}
    for seed in seeds:
        for trace in evaluation_trace_names:
            pair = paired_by_seed_trace[(seed, trace)]
            if set(pair) != {"static", "q-learning"}:
                raise ValueError(f"par incompleto para seed={seed}, trace={trace}")
            for metric in metrics:
                deltas[(seed, trace, metric)] = (
                    float(pair["q-learning"][metric])
                    - float(pair["static"][metric])
                )

    def append_row(scope: str, trace: str, metric: str, values: Sequence[float]) -> None:
        stats = confidence_interval_95(values)
        rows.append(
            {
                "scope": scope,
                "trace": trace,
                "metric": metric,
                "better_when": BETTER_WHEN[metric],
                "delta_definition": "q-learning_minus_static",
                **stats,
                "ci95_excludes_zero": (
                    float(stats["ci95_low"]) > 0
                    or float(stats["ci95_high"]) < 0
                ),
            }
        )

    for trace in evaluation_trace_names:
        for metric in metrics:
            append_row(
                "per_trace",
                trace,
                metric,
                [deltas[(seed, trace, metric)] for seed in seeds],
            )

    for metric in metrics:
        per_seed_means = [
            fmean(
                deltas[(seed, trace, metric)]
                for trace in evaluation_trace_names
            )
            for seed in seeds
        ]
        append_row(
            "overall_per_seed",
            "all_evaluation_traces",
            metric,
            per_seed_means,
        )
    return rows


def execute_protocol(definition: ProtocolDefinition) -> ProtocolResult:
    training_scales = definition.training_trace_scales or tuple(
        1.0 for _ in definition.training_trace_paths
    )
    evaluation_scales = definition.evaluation_trace_scales or tuple(
        1.0 for _ in definition.evaluation_trace_paths
    )
    if len(training_scales) != len(definition.training_trace_paths):
        raise ValueError("training_trace_scales difere dos traces de treinamento")
    if len(evaluation_scales) != len(definition.evaluation_trace_paths):
        raise ValueError("evaluation_trace_scales difere dos traces de avaliação")
    training_traces = [
        (path.stem, [value * scale for value in load_bandwidth_trace(path)])
        for path, scale in zip(definition.training_trace_paths, training_scales)
    ]
    evaluation_traces = [
        (path.stem, [value * scale for value in load_bandwidth_trace(path)])
        for path, scale in zip(definition.evaluation_trace_paths, evaluation_scales)
    ]
    segment_manifest = (
        load_segment_manifest(definition.segment_manifest_path)
        if definition.segment_manifest_path is not None
        else None
    )
    metrics = METRICS + MANIFEST_METRICS if segment_manifest is not None else METRICS
    raw_runs: list[dict[str, object]] = []
    training_summary: list[dict[str, object]] = []
    models: dict[int, tuple[QLearningAgent, dict[str, object]]] = {}

    for seed in definition.seeds:
        experiment_config = replace(definition.experiment_config, seed=seed)
        training_config = replace(definition.training_config, seed=seed)
        agent, encoder, history, metadata = train_q_learning(
            training_traces,
            experiment_config,
            training_config,
            definition.reward_config,
            trace_augmentation=definition.trace_augmentation,
            segment_manifest=segment_manifest,
        )
        models[seed] = (agent, metadata)
        final_window = history[-min(50, len(history)) :]
        training_summary.append(
            {
                "training_seed": seed,
                "episodes": len(history),
                "final_epsilon": agent.epsilon,
                "visited_states": int((abs(agent.q_table).sum(axis=1) > 0).sum()),
                "total_states": agent.state_space_size,
                "mean_reward_last_window": fmean(
                    float(row["mean_reward"]) for row in final_window
                ),
                "mean_rebuffering_last_window_s": fmean(
                    float(row["rebuffering_s"]) for row in final_window
                ),
            }
        )

        for trace_index, (trace_name, trace) in enumerate(evaluation_traces):
            _, static_summary = run_static_experiment(
                trace,
                experiment_config,
                segment_manifest=segment_manifest,
            )
            evaluation_seed = seed * 1009 + trace_index
            evaluation_agent = clone_agent(agent, evaluation_seed)
            _, q_summary = run_q_learning_experiment(
                trace,
                experiment_config,
                evaluation_agent,
                encoder,
                definition.reward_config,
                segment_manifest=segment_manifest,
                startup_guard=definition.training_config.startup_guard,
            )
            for summary in (static_summary, q_summary):
                raw_runs.append(
                    {
                        "training_seed": seed,
                        "policy_seed": (
                            evaluation_seed
                            if summary["controller"] == "q-learning"
                            else ""
                        ),
                        "trace": trace_name,
                        "controller": summary["controller"],
                        **{
                            metric: float(summary[metric])
                            for metric in metrics
                        },
                    }
                )

    trace_names = [name for name, _ in evaluation_traces]
    aggregate = _aggregate(raw_runs, definition.seeds, trace_names, metrics)
    paired = _paired_differences(raw_runs, definition.seeds, trace_names, metrics)
    return ProtocolResult(
        raw_runs=raw_runs,
        aggregate=aggregate,
        paired_differences=paired,
        training_summary=training_summary,
        metrics=metrics,
        models=models,
    )


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"não há dados para salvar em {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0].keys()),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def save_protocol_result(
    definition: ProtocolDefinition,
    result: ProtocolResult,
    output_dir: str | Path,
) -> dict[str, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    paths = {
        "raw_runs": destination / "raw_runs.csv",
        "aggregate": destination / "aggregate.csv",
        "paired_differences": destination / "paired_differences.csv",
        "training_summary": destination / "training_summary.csv",
        "manifest": destination / "manifest.json",
    }
    _write_csv(paths["raw_runs"], result.raw_runs)
    _write_csv(paths["aggregate"], result.aggregate)
    _write_csv(paths["paired_differences"], result.paired_differences)
    _write_csv(paths["training_summary"], result.training_summary)

    model_dir = destination / "models"
    model_paths: dict[int, str] = {}
    for seed, (agent, metadata) in result.models.items():
        model_path = agent.save(
            model_dir / f"q_learning_seed_{seed}.npz",
            metadata,
        )
        model_paths[seed] = str(model_path.relative_to(destination))

    segment_manifest = (
        load_segment_manifest(definition.segment_manifest_path)
        if definition.segment_manifest_path is not None
        else None
    )

    manifest: dict[str, Any] = {
        "protocol_version": definition.protocol_version,
        "confidence_level": definition.confidence_level,
        "confidence_method": "two-sided Student t interval for the mean",
        "overall_method": (
            "average evaluation traces within each seed, then compute CI across seeds"
        ),
        "delta_definition": "q-learning_minus_static",
        "metrics": list(result.metrics),
        "better_when": dict(BETTER_WHEN),
        "seeds": list(definition.seeds),
        "training_traces": [
            {"path": path.name, "bandwidth_scale": scale}
            for path, scale in zip(
                definition.training_trace_paths,
                definition.training_trace_scales
                or tuple(1.0 for _ in definition.training_trace_paths),
            )
        ],
        "evaluation_traces": [
            {"path": path.name, "bandwidth_scale": scale}
            for path, scale in zip(
                definition.evaluation_trace_paths,
                definition.evaluation_trace_scales
                or tuple(1.0 for _ in definition.evaluation_trace_paths),
            )
        ],
        "experiment_config": asdict(definition.experiment_config),
        "training_config": asdict(definition.training_config),
        "reward_config": asdict(definition.reward_config),
        "trace_augmentation": (
            asdict(definition.trace_augmentation)
            if definition.trace_augmentation is not None
            else None
        ),
        "segment_manifest": (
            segment_manifest.metadata()
            if segment_manifest is not None
            else None
        ),
        "models": model_paths,
    }
    with paths["manifest"].open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return paths
