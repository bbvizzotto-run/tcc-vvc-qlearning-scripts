"""Compara baseline e Q-Learning sob o mesmo trace e configuração."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from experiment import load_bandwidth_trace, run_static_experiment
from q_learning_pipeline import components_from_model, run_q_learning_experiment
from segment_manifest import load_segment_manifest


COMPARISON_FIELDS = (
    "trace",
    "controller",
    "seed",
    "segments",
    "video_duration_s",
    "startup_delay_s",
    "rebuffering_s",
    "rebuffering_rate_percent",
    "average_bitrate_kbps",
    "average_payload_bitrate_kbps",
    "buffer_mean_s",
    "buffer_std_s",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compara os controladores no mesmo trace.",
    )
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--segment-manifest",
        type=Path,
        help="CSV opcional com duração e tamanho medidos por representação",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--segments", type=int)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    trace = load_bandwidth_trace(args.trace)
    segment_manifest = (
        load_segment_manifest(args.segment_manifest)
        if args.segment_manifest is not None
        else None
    )
    agent, encoder, config, reward_config, _ = components_from_model(
        args.model,
        seed=args.seed,
    )
    _, static_summary = run_static_experiment(
        trace,
        config,
        args.segments,
        segment_manifest,
    )
    _, q_summary = run_q_learning_experiment(
        trace,
        config,
        agent,
        encoder,
        reward_config,
        args.segments,
        segment_manifest,
    )
    rows = []
    for summary in (static_summary, q_summary):
        row = {
            "trace": args.trace.stem,
            "seed": args.seed,
        }
        row.update(
            {
                field: summary[field]
                for field in COMPARISON_FIELDS
                if field not in row
            }
        )
        rows.append(row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=COMPARISON_FIELDS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"Comparação: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
