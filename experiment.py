"""Orquestração e persistência dos experimentos de streaming."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean, pstdev
from typing import Sequence

from controllers import StaticThresholdController
from streaming_env import StreamingConfig, StreamingEnvironment


@dataclass(frozen=True)
class ExperimentConfig:
    bitrates_kbps: tuple[int, ...] = (500, 1000, 2000, 4000)
    segment_duration_s: float = 2.0
    startup_buffer_s: float = 4.0
    max_buffer_s: float = 20.0
    low_buffer_s: float = 4.0
    high_buffer_s: float = 10.0
    seed: int = 42


def load_bandwidth_trace(path: str | Path) -> list[float]:
    """Lê CSV com as colunas ``segment`` e ``bandwidth_kbps``."""

    values: list[float] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "bandwidth_kbps" not in reader.fieldnames:
            raise ValueError("o trace deve conter a coluna bandwidth_kbps")
        for row_number, row in enumerate(reader, start=2):
            try:
                bandwidth = float(row["bandwidth_kbps"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"largura de banda inválida na linha {row_number}") from exc
            if bandwidth <= 0:
                raise ValueError(f"largura de banda não positiva na linha {row_number}")
            values.append(bandwidth)
    if not values:
        raise ValueError("o trace não contém amostras")
    return values


def run_static_experiment(
    bandwidth_trace_kbps: Sequence[float],
    config: ExperimentConfig,
    segments: int | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    if segments is not None and segments <= 0:
        raise ValueError("segments deve ser positivo")

    trace = list(bandwidth_trace_kbps)
    if segments is not None:
        if segments > len(trace):
            raise ValueError("segments excede o número de amostras do trace")
        trace = trace[:segments]

    environment = StreamingEnvironment(
        trace,
        StreamingConfig(
            segment_duration_s=config.segment_duration_s,
            startup_buffer_s=config.startup_buffer_s,
            max_buffer_s=config.max_buffer_s,
        ),
    )
    controller = StaticThresholdController(
        config.bitrates_kbps,
        low_buffer_s=config.low_buffer_s,
        high_buffer_s=config.high_buffer_s,
    )

    rows: list[dict[str, object]] = []
    while not environment.done:
        decision = controller.select_bitrate(environment.buffer_s)
        result = environment.step(decision.bitrate_kbps)
        row = result.to_dict()
        row["action"] = decision.action
        rows.append(row)

    summary: dict[str, object] = environment.summary()
    bitrates = [float(row["bitrate_kbps"]) for row in rows]
    buffers = [float(row["buffer_after_s"]) for row in rows]
    summary.update(
        {
            "controller": "static",
            "seed": config.seed,
            "average_bitrate_kbps": fmean(bitrates),
            "buffer_mean_s": fmean(buffers),
            "buffer_std_s": pstdev(buffers),
            "configuration": asdict(config),
        }
    )
    return rows, summary


def save_results(
    rows: Sequence[dict[str, object]],
    summary: dict[str, object],
    output_csv: str | Path,
) -> tuple[Path, Path]:
    if not rows:
        raise ValueError("não há resultados para salvar")

    csv_path = Path(output_csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary_path = csv_path.with_suffix(".summary.json")
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return csv_path, summary_path
