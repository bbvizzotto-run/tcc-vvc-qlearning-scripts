"""Protocolo pareado para Q-Learning e baselines ABR competitivos."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any, Mapping, Sequence

from abr_baselines import (
    BolaConfig,
    BolaController,
    RobustMpcConfig,
    RobustMpcController,
    ThroughputConfig,
    ThroughputController,
)
from controllers import StaticThresholdController
from experimental_protocol import (
    BETTER_WHEN,
    ProtocolDefinition,
    clone_agent,
    confidence_interval_95,
    load_protocol_definition,
)
from experiment import ExperimentConfig, load_bandwidth_trace
from q_learning_pipeline import (
    RewardConfig,
    calculate_reward,
    run_q_learning_experiment,
    train_q_learning,
)
from segment_manifest import SegmentManifest, load_segment_manifest
from streaming_env import StreamingConfig, StreamingEnvironment


CONTROLLERS: tuple[str, ...] = (
    "static",
    "throughput",
    "bola-basic",
    "robust-mpc",
    "q-learning",
)
BASELINES: tuple[str, ...] = CONTROLLERS[:-1]
METRICS: tuple[str, ...] = (
    "startup_delay_s",
    "rebuffering_s",
    "rebuffering_rate_percent",
    "average_bitrate_kbps",
    "average_payload_bitrate_kbps",
    "buffer_mean_s",
    "buffer_std_s",
    "mean_objective_reward",
    "switch_count",
    "high_representation_fraction_percent",
)
COMPARISON_BETTER_WHEN: Mapping[str, str] = {
    **BETTER_WHEN,
    "mean_objective_reward": "higher",
    "switch_count": "lower",
    "high_representation_fraction_percent": "descriptive",
}


@dataclass(frozen=True)
class AbrComparisonDefinition:
    source_path: Path
    comparison_version: int
    base_protocol: ProtocolDefinition
    throughput_config: ThroughputConfig
    bola_config: BolaConfig
    robust_mpc_config: RobustMpcConfig
    parameter_policy: str
    study_status: str
    references: Mapping[str, str]


@dataclass
class AbrComparisonResult:
    raw_runs: list[dict[str, object]]
    aggregate: list[dict[str, object]]
    paired_differences: list[dict[str, object]]
    training_summary: list[dict[str, object]]
    metrics: tuple[str, ...] = METRICS


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_abr_comparison_definition(
    path: str | Path,
) -> AbrComparisonDefinition:
    source_path = Path(path).resolve()
    with source_path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    root = source_path.parent
    base_path = (root / raw["base_protocol"]).resolve()
    if not base_path.is_file():
        raise ValueError("o protocolo-base da comparação não existe")
    base = load_protocol_definition(base_path)
    if base.segment_manifest_path is None:
        raise ValueError("a comparação ABR requer manifesto de segmentos")
    parameter_policy = str(raw["parameter_policy"])
    if parameter_policy != "frozen_before_first_execution_no_evaluation_tuning":
        raise ValueError("a política deve congelar parâmetros antes da execução")
    references = raw.get("references", {})
    if not isinstance(references, Mapping):
        raise ValueError("references deve ser um objeto")
    return AbrComparisonDefinition(
        source_path=source_path,
        comparison_version=int(raw["comparison_version"]),
        base_protocol=base,
        throughput_config=ThroughputConfig(**raw["throughput"]),
        bola_config=BolaConfig(**raw["bola_basic"]),
        robust_mpc_config=RobustMpcConfig(**raw["robust_mpc"]),
        parameter_policy=parameter_policy,
        study_status=str(raw["study_status"]),
        references={str(key): str(value) for key, value in references.items()},
    )


def _summary_metrics(
    rows: Sequence[dict[str, object]],
    environment: StreamingEnvironment,
    controller_name: str,
    total_reward: float,
    bitrates_kbps: Sequence[int],
) -> dict[str, object]:
    summary = environment.summary()
    selected = [int(row["bitrate_kbps"]) for row in rows]
    buffers = [float(row["buffer_after_s"]) for row in rows]
    payload_kbits = sum(float(row["segment_size_kbits"]) for row in rows)
    video_duration_s = float(summary["video_duration_s"])
    switches = sum(
        current != previous
        for previous, current in zip(selected, selected[1:])
    )
    summary.update(
        {
            "controller": controller_name,
            "average_bitrate_kbps": fmean(selected),
            "average_payload_bitrate_kbps": payload_kbits / video_duration_s,
            "buffer_mean_s": fmean(buffers),
            "buffer_std_s": pstdev(buffers),
            "mean_objective_reward": total_reward / len(rows),
            "switch_count": switches,
            "high_representation_fraction_percent": 100.0
            * sum(bitrate == max(bitrates_kbps) for bitrate in selected)
            / len(selected),
        }
    )
    return summary


def run_baseline_experiment(
    controller_name: str,
    bandwidth_trace_kbps: Sequence[float],
    experiment_config: ExperimentConfig,
    reward_config: RewardConfig,
    segment_manifest: SegmentManifest,
    throughput_config: ThroughputConfig | None = None,
    bola_config: BolaConfig | None = None,
    robust_mpc_config: RobustMpcConfig | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Executa um baseline sem expor a amostra de banda ainda não observada."""

    trace = list(bandwidth_trace_kbps)
    streaming_config = StreamingConfig(
        segment_duration_s=experiment_config.segment_duration_s,
        startup_buffer_s=experiment_config.startup_buffer_s,
        max_buffer_s=experiment_config.max_buffer_s,
    )
    environment = StreamingEnvironment(
        trace,
        streaming_config,
        segment_manifest=segment_manifest,
    )
    if controller_name == "static":
        controller: Any = StaticThresholdController(
            experiment_config.bitrates_kbps,
            experiment_config.low_buffer_s,
            experiment_config.high_buffer_s,
        )
    elif controller_name == "throughput":
        controller = ThroughputController(
            experiment_config.bitrates_kbps,
            throughput_config,
        )
    elif controller_name == "bola-basic":
        controller = BolaController(
            experiment_config.bitrates_kbps,
            bola_config,
        )
    elif controller_name == "robust-mpc":
        controller = RobustMpcController(
            experiment_config.bitrates_kbps,
            streaming_config,
            reward_config,
            segment_manifest,
            robust_mpc_config,
        )
    else:
        raise ValueError(f"baseline desconhecido: {controller_name}")

    rows: list[dict[str, object]] = []
    total_reward = 0.0
    previous_bitrate = experiment_config.bitrates_kbps[0]
    while not environment.done:
        if controller_name == "static":
            decision = controller.select_bitrate(environment.buffer_s)
        elif controller_name == "throughput":
            decision = controller.select_bitrate()
        elif controller_name == "bola-basic":
            decision = controller.select_bitrate(environment.buffer_s)
        else:
            decision = controller.select_bitrate(
                buffer_s=environment.buffer_s,
                segment_index=environment.segment_index,
                playback_started=environment.playback_started,
                remaining_segments=len(trace) - environment.segment_index,
            )
        result = environment.step(decision.bitrate_kbps)
        reward = calculate_reward(
            result=result,
            previous_bitrate_kbps=previous_bitrate,
            min_bitrate_kbps=experiment_config.bitrates_kbps[0],
            max_bitrate_kbps=experiment_config.bitrates_kbps[-1],
            segment_duration_s=result.segment_duration_s,
            config=reward_config,
        )
        if controller_name in {"throughput", "robust-mpc"}:
            controller.observe(result)
        row = result.to_dict()
        row.update({"action": decision.action, **asdict(reward)})
        rows.append(row)
        total_reward += reward.reward
        previous_bitrate = decision.bitrate_kbps

    return rows, _summary_metrics(
        rows,
        environment,
        controller_name,
        total_reward,
        experiment_config.bitrates_kbps,
    )


def _q_learning_metrics(
    rows: Sequence[dict[str, object]],
    summary: Mapping[str, object],
    bitrates_kbps: Sequence[int],
) -> dict[str, object]:
    selected = [int(row["bitrate_kbps"]) for row in rows]
    enriched = dict(summary)
    enriched.update(
        {
            "mean_objective_reward": float(summary["mean_reward"]),
            "switch_count": sum(
                current != previous
                for previous, current in zip(selected, selected[1:])
            ),
            "high_representation_fraction_percent": 100.0
            * sum(bitrate == max(bitrates_kbps) for bitrate in selected)
            / len(selected),
        }
    )
    return enriched


def _aggregate(
    raw_runs: Sequence[dict[str, object]],
    seeds: Sequence[int],
    trace_names: Sequence[str],
    metrics: Sequence[str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for trace in trace_names:
        for controller in CONTROLLERS:
            selected = [
                row
                for row in raw_runs
                if row["trace"] == trace and row["controller"] == controller
            ]
            for metric in metrics:
                rows.append(
                    {
                        "scope": "per_trace",
                        "trace": trace,
                        "controller": controller,
                        "metric": metric,
                        "better_when": COMPARISON_BETTER_WHEN[metric],
                        **confidence_interval_95(
                            [float(row[metric]) for row in selected]
                        ),
                    }
                )
    for controller in CONTROLLERS:
        for metric in metrics:
            per_seed = [
                fmean(
                    float(row[metric])
                    for row in raw_runs
                    if int(row["training_seed"]) == seed
                    and row["controller"] == controller
                )
                for seed in seeds
            ]
            rows.append(
                {
                    "scope": "overall_per_seed",
                    "trace": "all_evaluation_traces",
                    "controller": controller,
                    "metric": metric,
                    "better_when": COMPARISON_BETTER_WHEN[metric],
                    **confidence_interval_95(per_seed),
                }
            )
    return rows


def _paired_differences(
    raw_runs: Sequence[dict[str, object]],
    seeds: Sequence[int],
    trace_names: Sequence[str],
    metrics: Sequence[str],
) -> list[dict[str, object]]:
    indexed = {
        (int(row["training_seed"]), str(row["trace"]), str(row["controller"])): row
        for row in raw_runs
    }
    rows: list[dict[str, object]] = []

    def append(
        baseline: str,
        scope: str,
        trace: str,
        metric: str,
        values: Sequence[float],
    ) -> None:
        stats = confidence_interval_95(values)
        rows.append(
            {
                "scope": scope,
                "trace": trace,
                "baseline": baseline,
                "metric": metric,
                "better_when": COMPARISON_BETTER_WHEN[metric],
                "delta_definition": f"q-learning_minus_{baseline}",
                **stats,
                "ci95_excludes_zero": (
                    float(stats["ci95_low"]) > 0
                    or float(stats["ci95_high"]) < 0
                ),
            }
        )

    for baseline in BASELINES:
        for trace in trace_names:
            for metric in metrics:
                append(
                    baseline,
                    "per_trace",
                    trace,
                    metric,
                    [
                        float(indexed[(seed, trace, "q-learning")][metric])
                        - float(indexed[(seed, trace, baseline)][metric])
                        for seed in seeds
                    ],
                )
        for metric in metrics:
            append(
                baseline,
                "overall_per_seed",
                "all_evaluation_traces",
                metric,
                [
                    fmean(
                        float(indexed[(seed, trace, "q-learning")][metric])
                        - float(indexed[(seed, trace, baseline)][metric])
                        for trace in trace_names
                    )
                    for seed in seeds
                ],
            )
    return rows


def execute_abr_comparison(
    definition: AbrComparisonDefinition,
) -> AbrComparisonResult:
    base = definition.base_protocol
    training_scales = base.training_trace_scales or tuple(
        1.0 for _ in base.training_trace_paths
    )
    evaluation_scales = base.evaluation_trace_scales or tuple(
        1.0 for _ in base.evaluation_trace_paths
    )
    training_traces = [
        (path.stem, [value * scale for value in load_bandwidth_trace(path)])
        for path, scale in zip(base.training_trace_paths, training_scales)
    ]
    evaluation_traces = [
        (path.stem, [value * scale for value in load_bandwidth_trace(path)])
        for path, scale in zip(base.evaluation_trace_paths, evaluation_scales)
    ]
    assert base.segment_manifest_path is not None
    segment_manifest = load_segment_manifest(base.segment_manifest_path)
    if definition.bola_config.buffer_target_s > base.experiment_config.max_buffer_s:
        raise ValueError("o alvo do BOLA excede o buffer máximo")

    raw_runs: list[dict[str, object]] = []
    training_summary: list[dict[str, object]] = []
    for seed in base.seeds:
        experiment = replace(base.experiment_config, seed=seed)
        training = replace(base.training_config, seed=seed)
        agent, encoder, history, _ = train_q_learning(
            training_traces,
            experiment,
            training,
            base.reward_config,
            trace_augmentation=base.trace_augmentation,
            segment_manifest=segment_manifest,
        )
        final_window = history[-min(50, len(history)) :]
        training_summary.append(
            {
                "training_seed": seed,
                "episodes": len(history),
                "final_epsilon": agent.epsilon,
                "visited_states": int((abs(agent.q_table).sum(axis=1) > 0).sum()),
                "total_states": agent.state_space_size,
                "q_table_sha256": hashlib.sha256(agent.q_table.tobytes()).hexdigest(),
                "mean_reward_last_window": fmean(
                    float(row["mean_reward"]) for row in final_window
                ),
                "mean_rebuffering_last_window_s": fmean(
                    float(row["rebuffering_s"]) for row in final_window
                ),
            }
        )
        for trace_index, (trace_name, trace) in enumerate(evaluation_traces):
            summaries: list[dict[str, object]] = []
            for baseline in BASELINES:
                _, summary = run_baseline_experiment(
                    baseline,
                    trace,
                    experiment,
                    base.reward_config,
                    segment_manifest,
                    definition.throughput_config,
                    definition.bola_config,
                    definition.robust_mpc_config,
                )
                summaries.append(summary)
            evaluation_seed = seed * 1009 + trace_index
            evaluation_agent = clone_agent(agent, evaluation_seed)
            q_rows, q_summary = run_q_learning_experiment(
                trace,
                experiment,
                evaluation_agent,
                encoder,
                base.reward_config,
                segment_manifest=segment_manifest,
            )
            summaries.append(
                _q_learning_metrics(
                    q_rows,
                    q_summary,
                    experiment.bitrates_kbps,
                )
            )
            for summary in summaries:
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
                            for metric in METRICS
                        },
                    }
                )

    trace_names = [name for name, _ in evaluation_traces]
    return AbrComparisonResult(
        raw_runs=raw_runs,
        aggregate=_aggregate(raw_runs, base.seeds, trace_names, METRICS),
        paired_differences=_paired_differences(
            raw_runs,
            base.seeds,
            trace_names,
            METRICS,
        ),
        training_summary=training_summary,
    )


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"não há dados para salvar em {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def save_abr_comparison_result(
    definition: AbrComparisonDefinition,
    result: AbrComparisonResult,
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
    base = definition.base_protocol
    assert base.segment_manifest_path is not None
    manifest = {
        "comparison_version": definition.comparison_version,
        "stage": "5.4a",
        "study_status": definition.study_status,
        "parameter_policy": definition.parameter_policy,
        "controllers": list(CONTROLLERS),
        "baselines": {
            "static": {
                "low_buffer_s": base.experiment_config.low_buffer_s,
                "high_buffer_s": base.experiment_config.high_buffer_s,
            },
            "throughput": asdict(definition.throughput_config),
            "bola_basic": asdict(definition.bola_config),
            "robust_mpc": asdict(definition.robust_mpc_config),
        },
        "decision_information_policy": (
            "only completed-segment throughput, current buffer, and public "
            "segment metadata; no current-segment bandwidth"
        ),
        "reward_scope": (
            "the frozen project objective includes quality, post-startup "
            "rebuffering, switching, and low buffer; startup delay is reported "
            "as a separate metric but is not part of the optimized objective"
        ),
        "confidence_level": base.confidence_level,
        "confidence_method": "two-sided Student t interval for the mean",
        "overall_method": (
            "average evaluation traces within each seed, then compute CI across seeds"
        ),
        "delta_definitions": [
            f"q-learning_minus_{baseline}" for baseline in BASELINES
        ],
        "metrics": list(result.metrics),
        "better_when": dict(COMPARISON_BETTER_WHEN),
        "base_protocol": {
            "path": base.source_path.name,
            "sha256": _sha256(base.source_path),
            "seeds": list(base.seeds),
            "experiment_config": asdict(base.experiment_config),
            "training_config": asdict(base.training_config),
            "reward_config": asdict(base.reward_config),
        },
        "segment_manifest": {
            **load_segment_manifest(base.segment_manifest_path).metadata(),
            "path": base.segment_manifest_path.name,
        },
        "references": dict(definition.references),
        "artifacts": {
            key: {"path": path.name, "sha256": _sha256(path)}
            for key, path in paths.items()
            if key != "manifest"
        },
        "model_artifacts": (
            "not persisted; deterministic q_table hashes are in training_summary.csv"
        ),
    }
    with paths["manifest"].open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return paths
