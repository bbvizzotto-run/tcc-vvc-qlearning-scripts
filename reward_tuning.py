"""Seleciona pesos de recompensa usando somente traces de validação."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from statistics import fmean
from typing import Any, Mapping, Sequence

from experiment import ExperimentConfig, load_bandwidth_trace, run_static_experiment
from experimental_protocol import (
    BETTER_WHEN,
    MANIFEST_METRICS,
    METRICS,
    ProtocolDefinition,
    clone_agent,
    confidence_interval_95,
    load_protocol_definition,
)
from q_learning_pipeline import (
    RewardConfig,
    run_q_learning_experiment,
    train_q_learning,
)
from segment_manifest import load_segment_manifest


PRIMARY_METRIC = "rebuffering_rate_percent"
SECONDARY_METRIC = "average_payload_bitrate_kbps"
SELECTION_METHOD = (
    "require the upper bound of the paired 95% CI for Q-Learning minus static "
    "rebuffering rate and, when configured, startup delay to be at most their "
    "non-inferiority margins; among eligible candidates maximize mean paired "
    "payload bitrate; if none is eligible, minimize failed constraints, then "
    "startup and rebuffering upper bounds"
)


@dataclass(frozen=True)
class RewardCandidate:
    candidate_id: str
    reward_config: RewardConfig


@dataclass(frozen=True)
class RewardTuningDefinition:
    source_path: Path
    tuning_version: int
    base_protocol: ProtocolDefinition
    validation_trace_paths: tuple[Path, ...]
    validation_trace_scales: tuple[float, ...]
    candidates: tuple[RewardCandidate, ...]
    noninferiority_margin_percent: float = 0.0
    startup_noninferiority_margin_s: float | None = None
    stage: str = "5.3a"
    selection_context: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class RewardTuningResult:
    raw_runs: list[dict[str, object]]
    paired_differences: list[dict[str, object]]
    candidate_selection: list[dict[str, object]]
    training_summary: list[dict[str, object]]
    selected_candidate_id: str
    selection_mode: str
    metrics: tuple[str, ...]


def _resolve_scaled_traces(
    root: Path,
    items: Sequence[str | Mapping[str, Any]],
) -> tuple[tuple[Path, ...], tuple[float, ...]]:
    paths: list[Path] = []
    scales: list[float] = []
    for item in items:
        if isinstance(item, str):
            raw_path = item
            scale = 1.0
        elif isinstance(item, Mapping):
            raw_path = str(item["path"])
            scale = float(item.get("bandwidth_scale", 1.0))
        else:
            raise ValueError("cada trace deve ser um caminho ou objeto")
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError("bandwidth_scale deve ser positivo e finito")
        paths.append((root / raw_path).resolve())
        scales.append(scale)
    resolved = tuple(paths)
    if not resolved or any(not path.is_file() for path in resolved):
        raise ValueError("um ou mais traces de validação não existem")
    return resolved, tuple(scales)


def load_reward_tuning_definition(path: str | Path) -> RewardTuningDefinition:
    source_path = Path(path).resolve()
    with source_path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    root = source_path.parent
    validation_paths, validation_scales = _resolve_scaled_traces(
        root,
        raw["validation_traces"],
    )
    candidates = tuple(
        RewardCandidate(
            candidate_id=str(item["id"]),
            reward_config=RewardConfig(**item["reward_config"]),
        )
        for item in raw["candidates"]
    )
    definition = RewardTuningDefinition(
        source_path=source_path,
        tuning_version=int(raw["tuning_version"]),
        base_protocol=load_protocol_definition(root / raw["base_protocol"]),
        validation_trace_paths=validation_paths,
        validation_trace_scales=validation_scales,
        candidates=candidates,
        noninferiority_margin_percent=float(
            raw.get("noninferiority_margin_percent", 0.0)
        ),
        startup_noninferiority_margin_s=(
            float(raw["startup_noninferiority_margin_s"])
            if raw.get("startup_noninferiority_margin_s") is not None
            else None
        ),
        stage=str(raw.get("stage", "5.3a")),
        selection_context=dict(raw.get("refinement_provenance", {})),
    )
    _validate_definition(definition)
    return definition


def _validate_definition(definition: RewardTuningDefinition) -> None:
    protocol = definition.base_protocol
    if protocol.segment_manifest_path is None:
        raise ValueError(
            "o ajuste DVB requer manifesto para medir bitrate útil do payload"
        )
    if len(definition.validation_trace_paths) != len(
        definition.validation_trace_scales
    ):
        raise ValueError("escalas e traces de validação devem ter o mesmo tamanho")
    if len(definition.candidates) < 2:
        raise ValueError("o ajuste requer ao menos dois candidatos")
    candidate_ids = [candidate.candidate_id for candidate in definition.candidates]
    if any(not candidate_id.strip() for candidate_id in candidate_ids):
        raise ValueError("os identificadores dos candidatos não podem ser vazios")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("os identificadores dos candidatos devem ser únicos")
    if not math.isfinite(definition.noninferiority_margin_percent):
        raise ValueError("a margem de não inferioridade deve ser finita")
    if (
        definition.startup_noninferiority_margin_s is not None
        and not math.isfinite(definition.startup_noninferiority_margin_s)
    ):
        raise ValueError("a margem de startup deve ser finita")
    if not definition.stage.strip():
        raise ValueError("stage não pode ser vazio")

    training = set(protocol.training_trace_paths)
    validation = set(definition.validation_trace_paths)
    evaluation = set(protocol.evaluation_trace_paths)
    if training.intersection(validation) or validation.intersection(evaluation):
        raise ValueError(
            "os traces de validação devem ser independentes de treino e avaliação"
        )
    names = [
        path.stem
        for path in (
            *protocol.training_trace_paths,
            *definition.validation_trace_paths,
            *protocol.evaluation_trace_paths,
        )
    ]
    if len(names) != len(set(names)):
        raise ValueError("os nomes dos traces devem ser únicos")


def _row(
    candidate_id: str,
    reward_config: RewardConfig | None,
    seed: int,
    policy_seed: int | str,
    trace: str,
    controller: str,
    summary: Mapping[str, object],
    metrics: Sequence[str],
) -> dict[str, object]:
    reward = (
        asdict(reward_config)
        if reward_config is not None
        else {key: "" for key in asdict(RewardConfig())}
    )
    return {
        "candidate_id": candidate_id,
        **reward,
        "training_seed": seed,
        "policy_seed": policy_seed,
        "trace": trace,
        "controller": controller,
        **{metric: float(summary[metric]) for metric in metrics},
    }


def _paired_differences(
    raw_runs: Sequence[dict[str, object]],
    candidates: Sequence[RewardCandidate],
    seeds: Sequence[int],
    trace_names: Sequence[str],
    metrics: Sequence[str],
) -> list[dict[str, object]]:
    static = {
        (int(row["training_seed"]), str(row["trace"])): row
        for row in raw_runs
        if row["controller"] == "static"
    }
    q_rows = {
        (
            str(row["candidate_id"]),
            int(row["training_seed"]),
            str(row["trace"]),
        ): row
        for row in raw_runs
        if row["controller"] == "q-learning"
    }
    rows: list[dict[str, object]] = []
    for candidate in candidates:
        reward = asdict(candidate.reward_config)
        for metric in metrics:
            for scope, trace_group in (
                *(("per_trace", (trace,)) for trace in trace_names),
                ("overall_per_seed", tuple(trace_names)),
            ):
                per_seed = [
                    fmean(
                        float(q_rows[(candidate.candidate_id, seed, trace)][metric])
                        - float(static[(seed, trace)][metric])
                        for trace in trace_group
                    )
                    for seed in seeds
                ]
                stats = confidence_interval_95(per_seed)
                rows.append(
                    {
                        "candidate_id": candidate.candidate_id,
                        **reward,
                        "scope": scope,
                        "trace": (
                            trace_group[0]
                            if scope == "per_trace"
                            else "all_validation_traces"
                        ),
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
    return rows


def _select_candidate(
    candidates: Sequence[RewardCandidate],
    paired_differences: Sequence[dict[str, object]],
    noninferiority_margin_percent: float,
    startup_noninferiority_margin_s: float | None = None,
) -> tuple[list[dict[str, object]], str, str]:
    overall = {
        (str(row["candidate_id"]), str(row["metric"])): row
        for row in paired_differences
        if row["scope"] == "overall_per_seed"
    }
    selection_rows: list[dict[str, object]] = []
    for candidate in candidates:
        rebuffer = overall[(candidate.candidate_id, PRIMARY_METRIC)]
        payload = overall[(candidate.candidate_id, SECONDARY_METRIC)]
        startup = overall.get((candidate.candidate_id, "startup_delay_s"))
        rebuffer_eligible = (
            float(rebuffer["ci95_high"]) <= noninferiority_margin_percent
        )
        startup_eligible = (
            startup_noninferiority_margin_s is None
            or (
                startup is not None
                and float(startup["ci95_high"])
                <= startup_noninferiority_margin_s
            )
        )
        eligible = rebuffer_eligible and startup_eligible
        selection_rows.append(
            {
                "candidate_id": candidate.candidate_id,
                **asdict(candidate.reward_config),
                "rebuffering_rate_delta_mean": rebuffer["mean"],
                "rebuffering_rate_delta_ci95_low": rebuffer["ci95_low"],
                "rebuffering_rate_delta_ci95_high": rebuffer["ci95_high"],
                "payload_bitrate_delta_mean_kbps": payload["mean"],
                "payload_bitrate_delta_ci95_low_kbps": payload["ci95_low"],
                "payload_bitrate_delta_ci95_high_kbps": payload["ci95_high"],
                "startup_delay_delta_mean_s": (
                    startup["mean"] if startup is not None else ""
                ),
                "startup_delay_delta_ci95_low_s": (
                    startup["ci95_low"] if startup is not None else ""
                ),
                "startup_delay_delta_ci95_high_s": (
                    startup["ci95_high"] if startup is not None else ""
                ),
                "noninferiority_margin_percent": noninferiority_margin_percent,
                "startup_noninferiority_margin_s": (
                    startup_noninferiority_margin_s
                    if startup_noninferiority_margin_s is not None
                    else ""
                ),
                "rebuffer_eligible": rebuffer_eligible,
                "startup_eligible": startup_eligible,
                "eligible": eligible,
                "selected": False,
                "rank": 0,
            }
        )

    eligible_rows = [row for row in selection_rows if row["eligible"]]
    if eligible_rows:
        selection_mode = "eligible_max_payload"
        ordered = sorted(
            selection_rows,
            key=lambda row: (
                not bool(row["eligible"]),
                -float(row["payload_bitrate_delta_mean_kbps"]),
                float(row["rebuffering_rate_delta_ci95_high"]),
                str(row["candidate_id"]),
            ),
        )
    else:
        selection_mode = "fallback_min_constraint_violations"
        ordered = sorted(
            selection_rows,
            key=lambda row: (
                int(not bool(row["startup_eligible"]))
                + int(not bool(row["rebuffer_eligible"])),
                (
                    float(row["startup_delay_delta_ci95_high_s"])
                    if row["startup_delay_delta_ci95_high_s"] != ""
                    else -math.inf
                ),
                float(row["rebuffering_rate_delta_ci95_high"]),
                float(row["rebuffering_rate_delta_mean"]),
                -float(row["payload_bitrate_delta_mean_kbps"]),
                str(row["candidate_id"]),
            ),
        )
    for rank, row in enumerate(ordered, start=1):
        row["rank"] = rank
    ordered[0]["selected"] = True
    selected_id = str(ordered[0]["candidate_id"])
    return ordered, selected_id, selection_mode


def execute_reward_tuning(
    definition: RewardTuningDefinition,
) -> RewardTuningResult:
    """Treina candidatos e os compara apenas em validação.

    Esta função não carrega nem executa nenhum trace de avaliação do protocolo.
    """

    _validate_definition(definition)
    protocol = definition.base_protocol
    training_scales = protocol.training_trace_scales or tuple(
        1.0 for _ in protocol.training_trace_paths
    )
    training_traces = [
        (path.stem, [value * scale for value in load_bandwidth_trace(path)])
        for path, scale in zip(protocol.training_trace_paths, training_scales)
    ]
    validation_traces = [
        (path.stem, [value * scale for value in load_bandwidth_trace(path)])
        for path, scale in zip(
            definition.validation_trace_paths,
            definition.validation_trace_scales,
        )
    ]
    segment_manifest = (
        load_segment_manifest(protocol.segment_manifest_path)
        if protocol.segment_manifest_path is not None
        else None
    )
    metrics = METRICS + MANIFEST_METRICS if segment_manifest is not None else METRICS
    raw_runs: list[dict[str, object]] = []
    training_summary: list[dict[str, object]] = []

    for seed in protocol.seeds:
        experiment_config: ExperimentConfig = replace(
            protocol.experiment_config,
            seed=seed,
        )
        for trace_name, trace in validation_traces:
            _, summary = run_static_experiment(
                trace,
                experiment_config,
                segment_manifest=segment_manifest,
            )
            raw_runs.append(
                _row("static", None, seed, "", trace_name, "static", summary, metrics)
            )

    for candidate in definition.candidates:
        for seed in protocol.seeds:
            experiment_config = replace(protocol.experiment_config, seed=seed)
            training_config = replace(protocol.training_config, seed=seed)
            agent, encoder, history, _ = train_q_learning(
                training_traces,
                experiment_config,
                training_config,
                candidate.reward_config,
                trace_augmentation=protocol.trace_augmentation,
                segment_manifest=segment_manifest,
            )
            final_window = history[-min(50, len(history)) :]
            training_summary.append(
                {
                    "candidate_id": candidate.candidate_id,
                    **asdict(candidate.reward_config),
                    "training_seed": seed,
                    "episodes": len(history),
                    "final_epsilon": agent.epsilon,
                    "visited_states": int(
                        (abs(agent.q_table).sum(axis=1) > 0).sum()
                    ),
                    "total_states": agent.state_space_size,
                    "mean_reward_last_window": fmean(
                        float(row["mean_reward"]) for row in final_window
                    ),
                    "mean_rebuffering_last_window_s": fmean(
                        float(row["rebuffering_s"]) for row in final_window
                    ),
                }
            )
            for trace_index, (trace_name, trace) in enumerate(validation_traces):
                policy_seed = seed * 1009 + 500 + trace_index
                evaluation_agent = clone_agent(agent, policy_seed)
                _, summary = run_q_learning_experiment(
                    trace,
                    experiment_config,
                    evaluation_agent,
                    encoder,
                    candidate.reward_config,
                    segment_manifest=segment_manifest,
                    startup_guard=training_config.startup_guard,
                )
                raw_runs.append(
                    _row(
                        candidate.candidate_id,
                        candidate.reward_config,
                        seed,
                        policy_seed,
                        trace_name,
                        "q-learning",
                        summary,
                        metrics,
                    )
                )

    trace_names = [name for name, _ in validation_traces]
    paired = _paired_differences(
        raw_runs,
        definition.candidates,
        protocol.seeds,
        trace_names,
        metrics,
    )
    selection, selected_id, mode = _select_candidate(
        definition.candidates,
        paired,
        definition.noninferiority_margin_percent,
        definition.startup_noninferiority_margin_s,
    )
    return RewardTuningResult(
        raw_runs=raw_runs,
        paired_differences=paired,
        candidate_selection=selection,
        training_summary=training_summary,
        selected_candidate_id=selected_id,
        selection_mode=mode,
        metrics=metrics,
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


def save_reward_tuning_result(
    definition: RewardTuningDefinition,
    result: RewardTuningResult,
    output_dir: str | Path,
    selected_protocol_path: str | Path,
) -> dict[str, Path]:
    destination = Path(output_dir)
    paths = {
        "raw_runs": destination / "validation_raw_runs.csv",
        "paired_differences": destination / "validation_paired_differences.csv",
        "candidate_selection": destination / "candidate_selection.csv",
        "training_summary": destination / "training_summary.csv",
        "manifest": destination / "manifest.json",
        "selected_protocol": Path(selected_protocol_path),
    }
    _write_csv(paths["raw_runs"], result.raw_runs)
    _write_csv(paths["paired_differences"], result.paired_differences)
    _write_csv(paths["candidate_selection"], result.candidate_selection)
    _write_csv(paths["training_summary"], result.training_summary)

    protocol = definition.base_protocol
    selected = next(
        candidate
        for candidate in definition.candidates
        if candidate.candidate_id == result.selected_candidate_id
    )
    manifest: dict[str, Any] = {
        "tuning_version": definition.tuning_version,
        "base_protocol": protocol.source_path.name,
        "confidence_level": protocol.confidence_level,
        "confidence_method": "two-sided Student t interval for the paired mean",
        "overall_method": "average validation traces within seed, then CI across seeds",
        "primary_metric": PRIMARY_METRIC,
        "secondary_metric": SECONDARY_METRIC,
        "selection_method": SELECTION_METHOD,
        "selection_mode": result.selection_mode,
        "selection_context": dict(definition.selection_context),
        "noninferiority_margin_percent": definition.noninferiority_margin_percent,
        "startup_noninferiority_margin_s": (
            definition.startup_noninferiority_margin_s
        ),
        "selected_candidate_id": result.selected_candidate_id,
        "selected_reward_config": asdict(selected.reward_config),
        "candidates": [
            {"id": candidate.candidate_id, "reward_config": asdict(candidate.reward_config)}
            for candidate in definition.candidates
        ],
        "seeds": list(protocol.seeds),
        "training_traces": [
            {"path": path.name, "bandwidth_scale": scale}
            for path, scale in zip(
                protocol.training_trace_paths,
                protocol.training_trace_scales
                or tuple(1.0 for _ in protocol.training_trace_paths),
            )
        ],
        "validation_traces": [
            {"path": path.name, "bandwidth_scale": scale}
            for path, scale in zip(
                definition.validation_trace_paths,
                definition.validation_trace_scales,
            )
        ],
        "evaluation_traces_frozen": [
            path.name for path in protocol.evaluation_trace_paths
        ],
        "evaluation_leakage_guard": (
            "execute_reward_tuning loads training and validation traces only; "
            "evaluation trace paths are recorded but never opened or executed"
        ),
        "metrics": list(result.metrics),
        "experiment_config": asdict(protocol.experiment_config),
        "training_config": asdict(protocol.training_config),
        "segment_manifest": (
            load_segment_manifest(protocol.segment_manifest_path).metadata()
            if protocol.segment_manifest_path is not None
            else None
        ),
    }
    paths["manifest"].parent.mkdir(parents=True, exist_ok=True)
    with paths["manifest"].open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    with protocol.source_path.open(encoding="utf-8") as handle:
        selected_protocol = json.load(handle)
    selected_protocol["protocol_version"] = int(
        selected_protocol["protocol_version"]
    ) + 1
    selected_protocol["reward_config"] = asdict(selected.reward_config)
    selected_protocol["selection_provenance"] = {
        "stage": definition.stage,
        "tuning_config": definition.source_path.name,
        "tuning_manifest": str(paths["manifest"]),
        "selected_candidate_id": result.selected_candidate_id,
        "evaluation_status": "frozen_not_executed_during_selection",
    }
    paths["selected_protocol"].parent.mkdir(parents=True, exist_ok=True)
    with paths["selected_protocol"].open("w", encoding="utf-8") as handle:
        json.dump(selected_protocol, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return paths
