"""Protocolo confirmatório balanceado entre múltiplos conteúdos VVC."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import fmean
from typing import Callable, Mapping, Sequence

from abr_baselines import BolaConfig, RobustMpcConfig, ThroughputConfig
from abr_comparison import BASELINES, CONTROLLERS, run_baseline_experiment
from experiment import ExperimentConfig, load_bandwidth_trace
from experimental_protocol import clone_agent, confidence_interval_95
from q_learning_pipeline import (
    RewardConfig,
    TrainingConfig,
    run_q_learning_experiment,
    train_q_learning,
)
from segment_manifest import SegmentManifest, load_segment_manifest


FINAL_EXECUTION_POLICY = "single_final_execution_after_versioned_freeze"
PARAMETER_POLICY = "frozen_before_first_execution_no_evaluation_tuning"
METRICS: tuple[str, ...] = (
    "startup_delay_s",
    "rebuffering_s",
    "rebuffering_rate_percent",
    "average_bitrate_kbps",
    "average_payload_bitrate_kbps",
    "buffer_mean_s",
    "buffer_std_s",
    "mean_objective_reward",
    "mean_quality_utility",
    "mean_psnr_y_db",
    "switch_count",
    "high_representation_fraction_percent",
)
BETTER_WHEN: Mapping[str, str] = {
    "startup_delay_s": "lower",
    "rebuffering_s": "lower",
    "rebuffering_rate_percent": "lower",
    "average_bitrate_kbps": "higher",
    "average_payload_bitrate_kbps": "higher",
    "buffer_mean_s": "descriptive",
    "buffer_std_s": "lower",
    "mean_objective_reward": "higher",
    "mean_quality_utility": "higher",
    "mean_psnr_y_db": "higher",
    "switch_count": "lower",
    "high_representation_fraction_percent": "descriptive",
}


@dataclass(frozen=True)
class TraceInput:
    trace_id: str
    path: Path
    bandwidth_scale: float = 1.0


@dataclass(frozen=True)
class ContentInput:
    content_id: str
    manifest_path: Path


@dataclass(frozen=True)
class ExperimentTemplate:
    segment_duration_s: float
    startup_buffer_s: float
    max_buffer_s: float
    low_buffer_s: float
    high_buffer_s: float

    def build(self, bitrates_kbps: Sequence[int], seed: int) -> ExperimentConfig:
        return ExperimentConfig(
            bitrates_kbps=tuple(int(value) for value in bitrates_kbps),
            segment_duration_s=self.segment_duration_s,
            startup_buffer_s=self.startup_buffer_s,
            max_buffer_s=self.max_buffer_s,
            low_buffer_s=self.low_buffer_s,
            high_buffer_s=self.high_buffer_s,
            seed=seed,
        )


@dataclass(frozen=True)
class MultiContentComparisonDefinition:
    source_path: Path
    comparison_version: int
    stage: str
    study_status: str
    parameter_policy: str
    execution_policy: str
    previous_holdout_status: str
    confidence_level: float
    seeds: tuple[int, ...]
    training_traces: tuple[TraceInput, ...]
    evaluation_traces: tuple[TraceInput, ...]
    contents: tuple[ContentInput, ...]
    expected_segments: int
    expected_representations: int
    experiment_template: ExperimentTemplate
    training_config: TrainingConfig
    reward_config: RewardConfig
    throughput_config: ThroughputConfig
    bola_config: BolaConfig
    robust_mpc_config: RobustMpcConfig
    primary_metrics: tuple[str, ...]
    secondary_metrics: tuple[str, ...]
    primary_contrast: Mapping[str, str]
    references: Mapping[str, str]


@dataclass
class MultiContentComparisonResult:
    raw_runs: list[dict[str, object]]
    aggregate: list[dict[str, object]]
    paired_differences: list[dict[str, object]]
    training_summary: list[dict[str, object]]
    metrics: tuple[str, ...] = METRICS


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_trace_inputs(
    root: Path,
    values: Sequence[Mapping[str, object]],
    split: str,
) -> tuple[TraceInput, ...]:
    traces: list[TraceInput] = []
    for item in values:
        trace_id = str(item["id"]).strip()
        path = (root / str(item["path"])).resolve()
        scale = float(item.get("bandwidth_scale", 1.0))
        if not trace_id:
            raise ValueError(f"id vazio em {split}_traces")
        if not path.is_file():
            raise ValueError(f"trace inexistente: {path}")
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError("bandwidth_scale deve ser positivo e finito")
        traces.append(TraceInput(trace_id, path, scale))
    if not traces:
        raise ValueError(f"declare ao menos um trace de {split}")
    if len({trace.trace_id for trace in traces}) != len(traces):
        raise ValueError(f"ids duplicados em {split}_traces")
    if len({trace.path for trace in traces}) != len(traces):
        raise ValueError(f"caminhos duplicados em {split}_traces")
    return tuple(traces)


def _validate_manifest(
    content: ContentInput,
    manifest: SegmentManifest,
    definition: MultiContentComparisonDefinition,
) -> None:
    if manifest.sequence != content.content_id:
        raise ValueError(
            f"content_id={content.content_id} difere da sequência "
            f"{manifest.sequence}"
        )
    if manifest.segment_count != definition.expected_segments:
        raise ValueError(
            f"{content.content_id} deve conter "
            f"{definition.expected_segments} segmentos"
        )
    if len(manifest.bitrates_kbps) != definition.expected_representations:
        raise ValueError(
            f"{content.content_id} deve conter "
            f"{definition.expected_representations} representações"
        )
    for segment in manifest.segment_indices:
        for bitrate in manifest.bitrates_kbps:
            metadata = manifest.get(segment, bitrate)
            if not math.isclose(
                metadata.duration_s,
                definition.experiment_template.segment_duration_s,
                rel_tol=0,
                abs_tol=1e-9,
            ):
                raise ValueError(
                    f"duração inesperada em {content.content_id}, "
                    f"segmento {segment}"
                )
            if metadata.psnr_y_db is None:
                raise ValueError(
                    f"PSNR-Y ausente em {content.content_id}, segmento {segment}"
                )


def load_multi_content_comparison_definition(
    path: str | Path,
) -> MultiContentComparisonDefinition:
    """Carrega e valida o protocolo sem interpretar os valores do holdout."""

    source_path = Path(path).resolve()
    with source_path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    root = source_path.parent

    seeds = tuple(int(seed) for seed in raw["seeds"])
    if len(seeds) < 2 or len(set(seeds)) != len(seeds):
        raise ValueError("use ao menos duas sementes distintas")
    if any(seed < 0 for seed in seeds):
        raise ValueError("sementes não podem ser negativas")

    parameter_policy = str(raw["parameter_policy"])
    if parameter_policy != PARAMETER_POLICY:
        raise ValueError("a política deve congelar parâmetros antes da execução")
    execution_policy = str(raw["execution_policy"])
    if execution_policy != FINAL_EXECUTION_POLICY:
        raise ValueError("o protocolo requer execução final única")
    previous_holdout_status = str(raw["previous_holdout_status"])
    if previous_holdout_status != "not_executed":
        raise ValueError("o holdout deve estar marcado como não executado")
    confidence_level = float(raw.get("confidence_level", 0.95))
    if confidence_level != 0.95:
        raise ValueError("esta versão implementa somente IC95%")

    training_traces = _load_trace_inputs(
        root, raw["training_traces"], "training"
    )
    evaluation_traces = _load_trace_inputs(
        root, raw["evaluation_traces"], "evaluation"
    )
    if {trace.path for trace in training_traces} & {
        trace.path for trace in evaluation_traces
    }:
        raise ValueError("traces de treino e avaliação devem ser disjuntos")

    contents = tuple(
        ContentInput(
            content_id=str(item["id"]).strip(),
            manifest_path=(root / str(item["segment_manifest"])).resolve(),
        )
        for item in raw["contents"]
    )
    if len(contents) < 2:
        raise ValueError("o protocolo multicontéudo requer ao menos dois conteúdos")
    if any(not item.content_id for item in contents):
        raise ValueError("content_id não pode ser vazio")
    if len({item.content_id for item in contents}) != len(contents):
        raise ValueError("content_id deve ser único")
    if len({item.manifest_path for item in contents}) != len(contents):
        raise ValueError("cada conteúdo deve usar um manifesto distinto")
    if any(not item.manifest_path.is_file() for item in contents):
        raise ValueError("um ou mais manifestos não existem")

    experiment_template = ExperimentTemplate(**raw["experiment_config"])
    training_raw = dict(raw["training_config"])
    training_raw["buffer_boundaries_s"] = tuple(
        training_raw["buffer_boundaries_s"]
    )
    training_raw["seed"] = seeds[0]
    training_config = TrainingConfig(**training_raw)
    reward_config = RewardConfig(**raw["reward_config"])
    if not training_config.startup_guard:
        raise ValueError("o protocolo congelado requer startup_guard")
    if reward_config.startup_weight <= 0:
        raise ValueError("o protocolo congelado requer penalidade de startup")
    if reward_config.target_buffer_s > experiment_template.max_buffer_s:
        raise ValueError("o buffer-alvo excede o buffer máximo")

    primary_metrics = tuple(str(value) for value in raw["primary_metrics"])
    secondary_metrics = tuple(str(value) for value in raw["secondary_metrics"])
    if set(primary_metrics) & set(secondary_metrics):
        raise ValueError("métricas primárias e secundárias devem ser disjuntas")
    if set(primary_metrics) | set(secondary_metrics) != set(METRICS):
        raise ValueError("as métricas declaradas devem cobrir o protocolo")
    primary_contrast_raw = raw["primary_contrast"]
    if not isinstance(primary_contrast_raw, Mapping):
        raise ValueError("primary_contrast deve ser um objeto")
    primary_contrast = {
        str(key): str(value) for key, value in primary_contrast_raw.items()
    }
    if primary_contrast.get("metric") not in primary_metrics:
        raise ValueError("a métrica do contraste primário deve ser primária")
    if primary_contrast.get("baseline") not in BASELINES:
        raise ValueError("baseline desconhecido no contraste primário")
    if primary_contrast.get("scope") != "overall_content_balanced_per_seed":
        raise ValueError("o contraste primário deve usar o escopo geral balanceado")
    if primary_contrast.get("alternative") != "two_sided":
        raise ValueError("o contraste primário deve ser bilateral")

    references = raw.get("references", {})
    if not isinstance(references, Mapping):
        raise ValueError("references deve ser um objeto")
    definition = MultiContentComparisonDefinition(
        source_path=source_path,
        comparison_version=int(raw["comparison_version"]),
        stage=str(raw["stage"]),
        study_status=str(raw["study_status"]),
        parameter_policy=parameter_policy,
        execution_policy=execution_policy,
        previous_holdout_status=previous_holdout_status,
        confidence_level=confidence_level,
        seeds=seeds,
        training_traces=training_traces,
        evaluation_traces=evaluation_traces,
        contents=contents,
        expected_segments=int(raw["expected_segments"]),
        expected_representations=int(raw["expected_representations"]),
        experiment_template=experiment_template,
        training_config=training_config,
        reward_config=reward_config,
        throughput_config=ThroughputConfig(**raw["throughput"]),
        bola_config=BolaConfig(**raw["bola_basic"]),
        robust_mpc_config=RobustMpcConfig(**raw["robust_mpc"]),
        primary_metrics=primary_metrics,
        secondary_metrics=secondary_metrics,
        primary_contrast=primary_contrast,
        references={str(key): str(value) for key, value in references.items()},
    )
    if definition.expected_segments <= 0:
        raise ValueError("expected_segments deve ser positivo")
    if definition.expected_representations < 2:
        raise ValueError("expected_representations deve ser ao menos dois")
    if definition.bola_config.buffer_target_s > experiment_template.max_buffer_s:
        raise ValueError("o alvo do BOLA excede o buffer máximo")
    for content in contents:
        _validate_manifest(
            content,
            load_segment_manifest(content.manifest_path),
            definition,
        )
    return definition


def _load_scaled_trace(trace: TraceInput) -> list[float]:
    return [
        value * trace.bandwidth_scale
        for value in load_bandwidth_trace(trace.path)
    ]


def _enrich_metrics(
    rows: Sequence[dict[str, object]],
    summary: Mapping[str, object],
    bitrates_kbps: Sequence[int],
) -> dict[str, object]:
    if not rows:
        raise ValueError("uma execução não pode produzir zero segmentos")
    psnr_values = [
        float(row["psnr_y_db"])
        for row in rows
        if row.get("psnr_y_db") is not None
    ]
    if len(psnr_values) != len(rows):
        raise ValueError("PSNR-Y deve estar presente em todos os segmentos")
    quality_values = [float(row["quality_utility"]) for row in rows]
    selected = [int(row["bitrate_kbps"]) for row in rows]
    enriched = dict(summary)
    enriched.update(
        {
            "mean_quality_utility": fmean(quality_values),
            "mean_psnr_y_db": fmean(psnr_values),
            "switch_count": sum(
                current != previous
                for previous, current in zip(selected, selected[1:])
            ),
            "high_representation_fraction_percent": 100.0
            * sum(value == max(bitrates_kbps) for value in selected)
            / len(selected),
        }
    )
    if "mean_objective_reward" not in enriched:
        enriched["mean_objective_reward"] = float(enriched["mean_reward"])
    return enriched


def _aggregate(
    raw_runs: Sequence[dict[str, object]],
    definition: MultiContentComparisonDefinition,
    metrics: Sequence[str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    content_ids = [content.content_id for content in definition.contents]
    trace_ids = [trace.trace_id for trace in definition.evaluation_traces]

    for content_id in content_ids:
        for trace_id in trace_ids:
            for controller in CONTROLLERS:
                selected = [
                    row
                    for row in raw_runs
                    if row["content"] == content_id
                    and row["trace"] == trace_id
                    and row["controller"] == controller
                ]
                for metric in metrics:
                    rows.append(
                        {
                            "scope": "per_content_trace",
                            "content": content_id,
                            "trace": trace_id,
                            "controller": controller,
                            "metric": metric,
                            "better_when": BETTER_WHEN[metric],
                            **confidence_interval_95(
                                [float(row[metric]) for row in selected]
                            ),
                        }
                    )

    for content_id in content_ids:
        for controller in CONTROLLERS:
            for metric in metrics:
                per_seed = [
                    fmean(
                        float(row[metric])
                        for row in raw_runs
                        if int(row["training_seed"]) == seed
                        and row["content"] == content_id
                        and row["controller"] == controller
                    )
                    for seed in definition.seeds
                ]
                rows.append(
                    {
                        "scope": "per_content_per_seed",
                        "content": content_id,
                        "trace": "all_evaluation_traces",
                        "controller": controller,
                        "metric": metric,
                        "better_when": BETTER_WHEN[metric],
                        **confidence_interval_95(per_seed),
                    }
                )

    for controller in CONTROLLERS:
        for metric in metrics:
            per_seed = [
                fmean(
                    fmean(
                        float(row[metric])
                        for row in raw_runs
                        if int(row["training_seed"]) == seed
                        and row["content"] == content_id
                        and row["controller"] == controller
                    )
                    for content_id in content_ids
                )
                for seed in definition.seeds
            ]
            rows.append(
                {
                    "scope": "overall_content_balanced_per_seed",
                    "content": "all_contents",
                    "trace": "all_evaluation_traces",
                    "controller": controller,
                    "metric": metric,
                    "better_when": BETTER_WHEN[metric],
                    **confidence_interval_95(per_seed),
                }
            )
    return rows


def _paired_differences(
    raw_runs: Sequence[dict[str, object]],
    definition: MultiContentComparisonDefinition,
    metrics: Sequence[str],
) -> list[dict[str, object]]:
    indexed = {
        (
            int(row["training_seed"]),
            str(row["content"]),
            str(row["trace"]),
            str(row["controller"]),
        ): row
        for row in raw_runs
    }
    if len(indexed) != len(raw_runs):
        raise ValueError("há execuções duplicadas na matriz multicontéudo")
    rows: list[dict[str, object]] = []
    content_ids = [content.content_id for content in definition.contents]
    trace_ids = [trace.trace_id for trace in definition.evaluation_traces]

    def difference(
        seed: int,
        content_id: str,
        trace_id: str,
        baseline: str,
        metric: str,
    ) -> float:
        return float(
            indexed[(seed, content_id, trace_id, "q-learning")][metric]
        ) - float(indexed[(seed, content_id, trace_id, baseline)][metric])

    def append(
        baseline: str,
        scope: str,
        content_id: str,
        trace_id: str,
        metric: str,
        values: Sequence[float],
    ) -> None:
        stats = confidence_interval_95(values)
        rows.append(
            {
                "scope": scope,
                "content": content_id,
                "trace": trace_id,
                "baseline": baseline,
                "metric": metric,
                "better_when": BETTER_WHEN[metric],
                "delta_definition": f"q-learning_minus_{baseline}",
                **stats,
                "ci95_excludes_zero": (
                    float(stats["ci95_low"]) > 0
                    or float(stats["ci95_high"]) < 0
                ),
            }
        )

    for baseline in BASELINES:
        for content_id in content_ids:
            for trace_id in trace_ids:
                for metric in metrics:
                    append(
                        baseline,
                        "per_content_trace",
                        content_id,
                        trace_id,
                        metric,
                        [
                            difference(
                                seed, content_id, trace_id, baseline, metric
                            )
                            for seed in definition.seeds
                        ],
                    )
            for metric in metrics:
                append(
                    baseline,
                    "per_content_per_seed",
                    content_id,
                    "all_evaluation_traces",
                    metric,
                    [
                        fmean(
                            difference(
                                seed, content_id, trace_id, baseline, metric
                            )
                            for trace_id in trace_ids
                        )
                        for seed in definition.seeds
                    ],
                )
        for metric in metrics:
            append(
                baseline,
                "overall_content_balanced_per_seed",
                "all_contents",
                "all_evaluation_traces",
                metric,
                [
                    fmean(
                        fmean(
                            difference(
                                seed, content_id, trace_id, baseline, metric
                            )
                            for trace_id in trace_ids
                        )
                        for content_id in content_ids
                    )
                    for seed in definition.seeds
                ],
            )
    return rows


def execute_multi_content_comparison(
    definition: MultiContentComparisonDefinition,
    progress: Callable[[str], None] | None = None,
) -> MultiContentComparisonResult:
    """Treina uma política por conteúdo/semente e avalia a matriz congelada."""

    training_traces = [
        (trace.trace_id, _load_scaled_trace(trace))
        for trace in definition.training_traces
    ]
    evaluation_traces = [
        (trace.trace_id, _load_scaled_trace(trace))
        for trace in definition.evaluation_traces
    ]
    for trace_id, values in evaluation_traces:
        if len(values) != definition.expected_segments:
            raise ValueError(
                f"o trace {trace_id} deve conter "
                f"{definition.expected_segments} amostras"
            )

    raw_runs: list[dict[str, object]] = []
    training_summary: list[dict[str, object]] = []
    total_trainings = len(definition.contents) * len(definition.seeds)
    training_index = 0
    for content_index, content in enumerate(definition.contents):
        manifest = load_segment_manifest(content.manifest_path)
        for seed in definition.seeds:
            training_index += 1
            if progress is not None:
                progress(
                    f"[{training_index}/{total_trainings}] "
                    f"conteúdo={content.content_id} seed={seed}"
                )
            experiment = definition.experiment_template.build(
                manifest.bitrates_kbps, seed
            )
            training = replace(definition.training_config, seed=seed)
            agent, encoder, history, _ = train_q_learning(
                training_traces,
                experiment,
                training,
                definition.reward_config,
                segment_manifest=manifest,
            )
            final_window = history[-min(50, len(history)) :]
            training_summary.append(
                {
                    "content": content.content_id,
                    "training_seed": seed,
                    "episodes": len(history),
                    "final_epsilon": agent.epsilon,
                    "visited_states": int(
                        (abs(agent.q_table).sum(axis=1) > 0).sum()
                    ),
                    "total_states": agent.state_space_size,
                    "q_table_sha256": hashlib.sha256(
                        agent.q_table.tobytes()
                    ).hexdigest(),
                    "mean_reward_last_window": fmean(
                        float(row["mean_reward"]) for row in final_window
                    ),
                    "mean_rebuffering_last_window_s": fmean(
                        float(row["rebuffering_s"]) for row in final_window
                    ),
                }
            )
            for trace_index, (trace_id, trace) in enumerate(evaluation_traces):
                summaries: list[dict[str, object]] = []
                for baseline in BASELINES:
                    baseline_rows, baseline_summary = run_baseline_experiment(
                        baseline,
                        trace,
                        experiment,
                        definition.reward_config,
                        manifest,
                        definition.throughput_config,
                        definition.bola_config,
                        definition.robust_mpc_config,
                    )
                    summaries.append(
                        _enrich_metrics(
                            baseline_rows,
                            baseline_summary,
                            manifest.bitrates_kbps,
                        )
                    )
                policy_seed = (
                    seed * 1_000_003 + content_index * 10_007 + trace_index
                )
                q_rows, q_summary = run_q_learning_experiment(
                    trace,
                    experiment,
                    clone_agent(agent, policy_seed),
                    encoder,
                    definition.reward_config,
                    segment_manifest=manifest,
                    startup_guard=definition.training_config.startup_guard,
                )
                summaries.append(
                    _enrich_metrics(q_rows, q_summary, manifest.bitrates_kbps)
                )
                for summary in summaries:
                    raw_runs.append(
                        {
                            "content": content.content_id,
                            "training_seed": seed,
                            "policy_seed": (
                                policy_seed
                                if summary["controller"] == "q-learning"
                                else ""
                            ),
                            "trace": trace_id,
                            "controller": summary["controller"],
                            **{
                                metric: float(summary[metric])
                                for metric in METRICS
                            },
                        }
                    )

    return MultiContentComparisonResult(
        raw_runs=raw_runs,
        aggregate=_aggregate(raw_runs, definition, METRICS),
        paired_differences=_paired_differences(
            raw_runs, definition, METRICS
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


def save_multi_content_comparison_result(
    definition: MultiContentComparisonDefinition,
    result: MultiContentComparisonResult,
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

    manifest = {
        "comparison_version": definition.comparison_version,
        "stage": definition.stage,
        "study_status": definition.study_status,
        "parameter_policy": definition.parameter_policy,
        "execution_policy": definition.execution_policy,
        "previous_holdout_status": definition.previous_holdout_status,
        "controllers": list(CONTROLLERS),
        "training_mode": (
            "one content-specific Q-table per content and seed; no pooling "
            "between contents"
        ),
        "decision_information_policy": (
            "only completed-segment throughput, current buffer, and public "
            "segment metadata; no current-segment bandwidth"
        ),
        "statistical_unit": "training_seed",
        "confidence_level": definition.confidence_level,
        "confidence_method": "two-sided Student t interval for the mean",
        "overall_method": (
            "average traces within each content and seed, then average "
            "contents with equal weight within each seed, then compute CI "
            "across seeds"
        ),
        "primary_metrics": list(definition.primary_metrics),
        "secondary_metrics": list(definition.secondary_metrics),
        "primary_contrast": dict(definition.primary_contrast),
        "multiplicity_policy": (
            "one pre-specified primary contrast; all other controller and "
            "metric comparisons are secondary or descriptive"
        ),
        "metrics": list(result.metrics),
        "better_when": dict(BETTER_WHEN),
        "delta_definitions": [
            f"q-learning_minus_{baseline}" for baseline in BASELINES
        ],
        "seeds": list(definition.seeds),
        "experiment_config": asdict(definition.experiment_template),
        "training_config": asdict(definition.training_config),
        "reward_config": asdict(definition.reward_config),
        "baselines": {
            "static": {
                "low_buffer_s": definition.experiment_template.low_buffer_s,
                "high_buffer_s": definition.experiment_template.high_buffer_s,
            },
            "throughput": asdict(definition.throughput_config),
            "bola_basic": asdict(definition.bola_config),
            "robust_mpc": asdict(definition.robust_mpc_config),
        },
        "comparison_config": {
            "path": definition.source_path.name,
            "sha256": _sha256(definition.source_path),
        },
        "training_traces": [
            {
                "id": trace.trace_id,
                "path": trace.path.name,
                "sha256": _sha256(trace.path),
                "bandwidth_scale": trace.bandwidth_scale,
            }
            for trace in definition.training_traces
        ],
        "evaluation_traces": [
            {
                "id": trace.trace_id,
                "path": trace.path.name,
                "sha256": _sha256(trace.path),
                "bandwidth_scale": trace.bandwidth_scale,
            }
            for trace in definition.evaluation_traces
        ],
        "contents": [
            {
                "id": content.content_id,
                "path": str(
                    content.manifest_path.relative_to(
                        definition.source_path.parent
                    )
                ),
                "sha256": _sha256(content.manifest_path),
                "manifest": load_segment_manifest(
                    content.manifest_path
                ).metadata(),
            }
            for content in definition.contents
        ],
        "references": dict(definition.references),
        "artifacts": {
            key: {"path": path.name, "sha256": _sha256(path)}
            for key, path in paths.items()
            if key != "manifest"
        },
        "model_artifacts": (
            "not persisted; deterministic q_table hashes are in "
            "training_summary.csv"
        ),
    }
    marker_path = destination / ".execution_started.json"
    if marker_path.is_file():
        manifest["execution_marker"] = {
            "path": marker_path.name,
            "sha256": _sha256(marker_path),
        }
    with paths["manifest"].open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return paths
