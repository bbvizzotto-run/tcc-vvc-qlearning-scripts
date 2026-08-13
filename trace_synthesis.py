"""Gera traces independentes e reproduzíveis para validação e holdout."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class TraceModel:
    segments: int
    regime_means_kbps: tuple[float, ...]
    transition_matrix: tuple[tuple[float, ...], ...]
    autoregressive_alpha: float
    log_noise_sigma: float
    minimum_kbps: float
    maximum_kbps: float

    def __post_init__(self) -> None:
        if self.segments <= 0:
            raise ValueError("segments deve ser positivo")
        if not self.regime_means_kbps or any(
            value <= 0 for value in self.regime_means_kbps
        ):
            raise ValueError("as médias dos regimes devem ser positivas")
        size = len(self.regime_means_kbps)
        if len(self.transition_matrix) != size or any(
            len(row) != size for row in self.transition_matrix
        ):
            raise ValueError("a matriz de transição deve ser quadrada")
        for row in self.transition_matrix:
            if any(value < 0 for value in row) or not math.isclose(
                sum(row), 1.0, rel_tol=0, abs_tol=1e-9
            ):
                raise ValueError("cada linha da matriz deve somar 1")
        if not 0 <= self.autoregressive_alpha < 1:
            raise ValueError("autoregressive_alpha deve pertencer a [0, 1)")
        if self.log_noise_sigma < 0:
            raise ValueError("log_noise_sigma não pode ser negativo")
        if self.minimum_kbps <= 0 or self.maximum_kbps <= self.minimum_kbps:
            raise ValueError("limites de banda inválidos")


@dataclass(frozen=True)
class TraceSpecification:
    trace_id: str
    split: str
    seed: int
    initial_regime: int
    path: Path

    def __post_init__(self) -> None:
        if not self.trace_id.strip():
            raise ValueError("trace_id não pode ser vazio")
        if self.split not in {"validation", "evaluation"}:
            raise ValueError("split deve ser validation ou evaluation")
        if self.seed < 0:
            raise ValueError("seed não pode ser negativa")


@dataclass(frozen=True)
class TraceSynthesisDefinition:
    source_path: Path
    generator_version: int
    model: TraceModel
    traces: tuple[TraceSpecification, ...]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_trace_synthesis_definition(
    path: str | Path,
) -> TraceSynthesisDefinition:
    source_path = Path(path).resolve()
    with source_path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    root = source_path.parent
    model_raw = raw["model"]
    model = TraceModel(
        segments=int(model_raw["segments"]),
        regime_means_kbps=tuple(
            float(value) for value in model_raw["regime_means_kbps"]
        ),
        transition_matrix=tuple(
            tuple(float(value) for value in row)
            for row in model_raw["transition_matrix"]
        ),
        autoregressive_alpha=float(model_raw["autoregressive_alpha"]),
        log_noise_sigma=float(model_raw["log_noise_sigma"]),
        minimum_kbps=float(model_raw["minimum_kbps"]),
        maximum_kbps=float(model_raw["maximum_kbps"]),
    )
    traces = tuple(
        TraceSpecification(
            trace_id=str(item["id"]),
            split=str(item["split"]),
            seed=int(item["seed"]),
            initial_regime=int(item["initial_regime"]),
            path=(root / item["path"]).resolve(),
        )
        for item in raw["traces"]
    )
    if len(traces) < 2:
        raise ValueError("declare ao menos dois traces")
    if len({trace.trace_id for trace in traces}) != len(traces):
        raise ValueError("os ids dos traces devem ser únicos")
    if len({trace.path for trace in traces}) != len(traces):
        raise ValueError("os caminhos dos traces devem ser únicos")
    if len({trace.seed for trace in traces}) != len(traces):
        raise ValueError("cada trace deve usar uma semente independente")
    if {trace.split for trace in traces} != {"validation", "evaluation"}:
        raise ValueError("declare traces para validação e avaliação")
    if any(
        trace.initial_regime < 0
        or trace.initial_regime >= len(model.regime_means_kbps)
        for trace in traces
    ):
        raise ValueError("initial_regime fora da faixa")
    return TraceSynthesisDefinition(
        source_path=source_path,
        generator_version=int(raw["generator_version"]),
        model=model,
        traces=traces,
    )


def generate_trace(
    model: TraceModel,
    specification: TraceSpecification,
) -> list[float]:
    """Amostra um modelo Markoviano com suavização AR(1) no domínio log."""

    rng = random.Random(specification.seed)
    regime = specification.initial_regime
    previous_log = math.log(model.regime_means_kbps[regime])
    values: list[float] = []
    for _ in range(model.segments):
        draw = rng.random()
        cumulative = 0.0
        for candidate, probability in enumerate(
            model.transition_matrix[regime]
        ):
            cumulative += probability
            if draw <= cumulative:
                regime = candidate
                break
        target_log = math.log(model.regime_means_kbps[regime])
        sampled_log = (
            model.autoregressive_alpha * previous_log
            + (1.0 - model.autoregressive_alpha) * target_log
            + rng.gauss(0.0, model.log_noise_sigma)
        )
        bandwidth = min(
            model.maximum_kbps,
            max(model.minimum_kbps, math.exp(sampled_log)),
        )
        values.append(round(bandwidth, 6))
        previous_log = math.log(bandwidth)
    return values


def _write_trace(path: Path, values: Sequence[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("segment", "bandwidth_kbps"))
        writer.writerows(enumerate(values))


def generate_trace_suite(
    definition: TraceSynthesisDefinition,
    provenance_path: str | Path,
    overwrite: bool = False,
) -> dict[str, Path]:
    destinations = [trace.path for trace in definition.traces]
    provenance = Path(provenance_path)
    existing = [path for path in (*destinations, provenance) if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "saídas já existem: " + ", ".join(str(path) for path in existing)
        )

    generated: dict[str, Path] = {}
    summaries: list[dict[str, Any]] = []
    for specification in definition.traces:
        values = generate_trace(definition.model, specification)
        _write_trace(specification.path, values)
        generated[specification.trace_id] = specification.path
        summaries.append(
            {
                "id": specification.trace_id,
                "split": specification.split,
                "seed": specification.seed,
                "initial_regime": specification.initial_regime,
                "path": str(
                    specification.path.relative_to(
                        definition.source_path.parent
                    )
                ),
                "sha256": _sha256(specification.path),
                "segments": len(values),
                "minimum_kbps": min(values),
                "mean_kbps": fmean(values),
                "maximum_kbps": max(values),
            }
        )

    module_path = Path(__file__).resolve()
    document: Mapping[str, Any] = {
        "generator_version": definition.generator_version,
        "method": "seeded Markov regimes with log-domain AR(1) smoothing",
        "source_trace_usage": "none; values are generated without resampling existing traces",
        "config": definition.source_path.name,
        "config_sha256": _sha256(definition.source_path),
        "generator_module": module_path.name,
        "generator_module_sha256": _sha256(module_path),
        "model": {
            "segments": definition.model.segments,
            "regime_means_kbps": list(definition.model.regime_means_kbps),
            "transition_matrix": [
                list(row) for row in definition.model.transition_matrix
            ],
            "autoregressive_alpha": (
                definition.model.autoregressive_alpha
            ),
            "log_noise_sigma": definition.model.log_noise_sigma,
            "minimum_kbps": definition.model.minimum_kbps,
            "maximum_kbps": definition.model.maximum_kbps,
        },
        "traces": summaries,
    }
    provenance.parent.mkdir(parents=True, exist_ok=True)
    with provenance.open("w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    generated["provenance"] = provenance
    return generated
