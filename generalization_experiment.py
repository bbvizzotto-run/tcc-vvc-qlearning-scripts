"""Compara treino original e treino robusto sem vazamento de avaliação."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from statistics import fmean
from typing import Any, Mapping, Sequence

from experiment import ExperimentConfig, load_bandwidth_trace, run_static_experiment
from experimental_protocol import (
    BETTER_WHEN,
    METRICS,
    ProtocolDefinition,
    ProtocolResult,
    clone_agent,
    confidence_interval_95,
    execute_protocol,
    load_protocol_definition,
)
from q_learning_pipeline import StateEncoder, run_q_learning_experiment


CONTROLLERS: tuple[str, ...] = (
    "static",
    "q-learning-standard",
    "q-learning-robust",
)

COMPARISONS: Mapping[str, tuple[str, str]] = {
    "standard_minus_static": ("q-learning-standard", "static"),
    "robust_minus_static": ("q-learning-robust", "static"),
    "robust_minus_standard": ("q-learning-robust", "q-learning-standard"),
}


@dataclass(frozen=True)
class GeneralizationDefinition:
    source_path: Path
    experiment_version: int
    standard_protocol: ProtocolDefinition
    robust_protocol: ProtocolDefinition
    validation_trace_paths: tuple[Path, ...]


@dataclass
class GeneralizationResult:
    raw_runs: list[dict[str, object]]
    paired_differences: list[dict[str, object]]
    training_summary: list[dict[str, object]]
    strategy_results: dict[str, ProtocolResult] = field(repr=False)


def load_generalization_definition(
    path: str | Path,
) -> GeneralizationDefinition:
    source_path = Path(path).resolve()
    with source_path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    root = source_path.parent
    validation_paths = tuple(
        (root / item).resolve() for item in raw["validation_traces"]
    )
    if not validation_paths or any(not item.is_file() for item in validation_paths):
        raise ValueError("um ou mais traces de validação não existem")

    definition = GeneralizationDefinition(
        source_path=source_path,
        experiment_version=int(raw["experiment_version"]),
        standard_protocol=load_protocol_definition(root / raw["standard_protocol"]),
        robust_protocol=load_protocol_definition(root / raw["robust_protocol"]),
        validation_trace_paths=validation_paths,
    )
    _validate_definition(definition)
    return definition


def _validate_definition(definition: GeneralizationDefinition) -> None:
    standard = definition.standard_protocol
    robust = definition.robust_protocol
    if standard.seeds != robust.seeds:
        raise ValueError("as estratégias devem usar as mesmas sementes")
    if standard.training_trace_paths != robust.training_trace_paths:
        raise ValueError("as estratégias devem usar os mesmos traces-base de treino")
    if standard.evaluation_trace_paths != robust.evaluation_trace_paths:
        raise ValueError("as estratégias devem usar os mesmos traces de avaliação")
    if standard.experiment_config != robust.experiment_config:
        raise ValueError("as estratégias devem usar o mesmo ambiente")
    if standard.training_config != robust.training_config:
        raise ValueError("somente a randomização de domínio pode diferir no treino")
    if standard.reward_config != robust.reward_config:
        raise ValueError("as estratégias devem usar a mesma recompensa")
    if standard.trace_augmentation is not None:
        raise ValueError("o protocolo original não pode usar aumento de traces")
    if robust.trace_augmentation is None:
        raise ValueError("o protocolo robusto deve configurar aumento de traces")

    reserved = set(standard.training_trace_paths) | set(
        standard.evaluation_trace_paths
    )
    if reserved.intersection(definition.validation_trace_paths):
        raise ValueError("traces de validação devem ser independentes")
    trace_names = [
        path.stem
        for path in (
            *standard.training_trace_paths,
            *definition.validation_trace_paths,
            *standard.evaluation_trace_paths,
        )
    ]
    if len(trace_names) != len(set(trace_names)):
        raise ValueError("os nomes dos traces devem ser únicos")


def _metric_row(
    dataset: str,
    seed: int,
    policy_seed: int | str,
    trace: str,
    controller: str,
    summary: Mapping[str, object],
) -> dict[str, object]:
    return {
        "dataset": dataset,
        "training_seed": seed,
        "policy_seed": policy_seed,
        "trace": trace,
        "controller": controller,
        **{metric: float(summary[metric]) for metric in METRICS},
    }


def _evaluation_rows(
    standard: ProtocolResult,
    robust: ProtocolResult,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in standard.raw_runs:
        controller = str(row["controller"])
        rows.append(
            {
                "dataset": "evaluation",
                **row,
                "controller": (
                    "q-learning-standard"
                    if controller == "q-learning"
                    else controller
                ),
            }
        )
    for row in robust.raw_runs:
        if row["controller"] != "q-learning":
            continue
        rows.append(
            {
                "dataset": "evaluation",
                **row,
                "controller": "q-learning-robust",
            }
        )
    return rows


def _validation_rows(
    definition: GeneralizationDefinition,
    standard: ProtocolResult,
    robust: ProtocolResult,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    traces = [
        (path.stem, load_bandwidth_trace(path))
        for path in definition.validation_trace_paths
    ]
    protocol = definition.standard_protocol
    encoder = StateEncoder(
        protocol.experiment_config.bitrates_kbps,
        protocol.training_config.buffer_boundaries_s,
    )

    for seed in protocol.seeds:
        config: ExperimentConfig = replace(protocol.experiment_config, seed=seed)
        for trace_index, (trace_name, trace) in enumerate(traces):
            _, static_summary = run_static_experiment(trace, config)
            rows.append(
                _metric_row(
                    "validation",
                    seed,
                    "",
                    trace_name,
                    "static",
                    static_summary,
                )
            )
            policy_seed = seed * 1009 + 100 + trace_index
            for strategy_name, result in (
                ("standard", standard),
                ("robust", robust),
            ):
                agent = clone_agent(result.models[seed][0], policy_seed)
                _, summary = run_q_learning_experiment(
                    trace,
                    config,
                    agent,
                    encoder,
                    protocol.reward_config,
                )
                rows.append(
                    _metric_row(
                        "validation",
                        seed,
                        policy_seed,
                        trace_name,
                        f"q-learning-{strategy_name}",
                        summary,
                    )
                )
    return rows


def _paired_differences(
    raw_runs: Sequence[dict[str, object]],
    seeds: Sequence[int],
) -> list[dict[str, object]]:
    grouped: dict[
        tuple[str, int, str],
        dict[str, dict[str, object]],
    ] = {}
    traces_by_dataset: dict[str, list[str]] = {}
    for row in raw_runs:
        dataset = str(row["dataset"])
        trace = str(row["trace"])
        key = (dataset, int(row["training_seed"]), trace)
        grouped.setdefault(key, {})[str(row["controller"])] = row
        traces_by_dataset.setdefault(dataset, [])
        if trace not in traces_by_dataset[dataset]:
            traces_by_dataset[dataset].append(trace)

    deltas: dict[tuple[str, int, str, str, str], float] = {}
    for (dataset, seed, trace), controllers in grouped.items():
        if set(controllers) != set(CONTROLLERS):
            raise ValueError(
                f"comparação incompleta: dataset={dataset}, seed={seed}, trace={trace}"
            )
        for comparison, (left, right) in COMPARISONS.items():
            for metric in METRICS:
                deltas[(dataset, seed, trace, comparison, metric)] = (
                    float(controllers[left][metric])
                    - float(controllers[right][metric])
                )

    rows: list[dict[str, object]] = []

    def append_row(
        dataset: str,
        scope: str,
        trace: str,
        comparison: str,
        metric: str,
        values: Sequence[float],
    ) -> None:
        stats = confidence_interval_95(values)
        rows.append(
            {
                "dataset": dataset,
                "scope": scope,
                "trace": trace,
                "comparison": comparison,
                "metric": metric,
                "better_when": BETTER_WHEN[metric],
                "n": stats["n"],
                "mean": stats["mean"],
                "std": stats["std"],
                "ci95_half_width": stats["ci95_half_width"],
                "ci95_low": stats["ci95_low"],
                "ci95_high": stats["ci95_high"],
                "ci95_excludes_zero": (
                    float(stats["ci95_low"]) > 0
                    or float(stats["ci95_high"]) < 0
                ),
            }
        )

    for dataset, traces in traces_by_dataset.items():
        for trace in traces:
            for comparison in COMPARISONS:
                for metric in METRICS:
                    append_row(
                        dataset,
                        "per_trace",
                        trace,
                        comparison,
                        metric,
                        [
                            deltas[(dataset, seed, trace, comparison, metric)]
                            for seed in seeds
                        ],
                    )
        for comparison in COMPARISONS:
            for metric in METRICS:
                per_seed_means = [
                    fmean(
                        deltas[(dataset, seed, trace, comparison, metric)]
                        for trace in traces
                    )
                    for seed in seeds
                ]
                append_row(
                    dataset,
                    "overall_per_seed",
                    f"all_{dataset}_traces",
                    comparison,
                    metric,
                    per_seed_means,
                )
    return rows


def execute_generalization_experiment(
    definition: GeneralizationDefinition,
) -> GeneralizationResult:
    _validate_definition(definition)
    standard = execute_protocol(definition.standard_protocol)
    robust = execute_protocol(definition.robust_protocol)
    raw_runs = _evaluation_rows(standard, robust)
    raw_runs.extend(_validation_rows(definition, standard, robust))
    training_summary = [
        {"strategy": strategy, **row}
        for strategy, result in (("standard", standard), ("robust", robust))
        for row in result.training_summary
    ]
    return GeneralizationResult(
        raw_runs=raw_runs,
        paired_differences=_paired_differences(
            raw_runs,
            definition.standard_protocol.seeds,
        ),
        training_summary=training_summary,
        strategy_results={"standard": standard, "robust": robust},
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


def save_generalization_result(
    definition: GeneralizationDefinition,
    result: GeneralizationResult,
    output_dir: str | Path,
) -> dict[str, Path]:
    destination = Path(output_dir)
    paths = {
        "raw_runs": destination / "raw_runs.csv",
        "paired_differences": destination / "paired_differences.csv",
        "training_summary": destination / "training_summary.csv",
        "manifest": destination / "manifest.json",
    }
    _write_csv(paths["raw_runs"], result.raw_runs)
    _write_csv(paths["paired_differences"], result.paired_differences)
    _write_csv(paths["training_summary"], result.training_summary)

    model_paths: dict[str, dict[int, str]] = {}
    for strategy, strategy_result in result.strategy_results.items():
        model_paths[strategy] = {}
        for seed, (agent, metadata) in strategy_result.models.items():
            model_path = agent.save(
                destination / "models" / strategy / f"q_learning_seed_{seed}.npz",
                metadata,
            )
            model_paths[strategy][seed] = str(model_path.relative_to(destination))

    standard = definition.standard_protocol
    robust = definition.robust_protocol
    manifest: dict[str, Any] = {
        "experiment_version": definition.experiment_version,
        "confidence_level": standard.confidence_level,
        "confidence_method": "two-sided Student t interval for the mean",
        "overall_method": (
            "average traces within each seed, then compute CI across seeds"
        ),
        "comparisons": dict(COMPARISONS),
        "seeds": list(standard.seeds),
        "training_traces": [path.name for path in standard.training_trace_paths],
        "validation_traces": [
            path.name for path in definition.validation_trace_paths
        ],
        "evaluation_traces": [path.name for path in standard.evaluation_trace_paths],
        "evaluation_leakage_guard": (
            "augmentation is generated exclusively from training traces; validation "
            "and evaluation traces are never passed to train_q_learning"
        ),
        "experiment_config": asdict(standard.experiment_config),
        "training_config": asdict(standard.training_config),
        "reward_config": asdict(standard.reward_config),
        "robust_trace_augmentation": asdict(robust.trace_augmentation),
        "models": model_paths,
    }
    paths["manifest"].parent.mkdir(parents=True, exist_ok=True)
    with paths["manifest"].open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return paths
