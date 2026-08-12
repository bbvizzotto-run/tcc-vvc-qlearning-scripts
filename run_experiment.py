"""Executa controladores estático ou Q-Learning no mesmo ambiente."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiment import (
    ExperimentConfig,
    load_bandwidth_trace,
    run_static_experiment,
    save_results,
)
from q_learning_pipeline import components_from_model, run_q_learning_experiment


def parse_bitrates(value: str) -> tuple[int, ...]:
    try:
        bitrates = tuple(int(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use bitrates inteiros separados por vírgula") from exc
    if not bitrates or any(bitrate <= 0 for bitrate in bitrates):
        raise argparse.ArgumentTypeError("todos os bitrates devem ser positivos")
    return bitrates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Executa um controlador no simulador de streaming.",
    )
    parser.add_argument(
        "--controller",
        choices=("static", "q-learning"),
        default="static",
    )
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--model",
        type=Path,
        help="modelo NPZ obrigatório para o controlador q-learning",
    )
    parser.add_argument("--segments", type=int)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bitrates", type=parse_bitrates, default=(500, 1000, 2000, 4000))
    parser.add_argument("--segment-duration", type=float, default=2.0)
    parser.add_argument("--startup-buffer", type=float, default=4.0)
    parser.add_argument("--max-buffer", type=float, default=20.0)
    parser.add_argument("--low-buffer", type=float, default=4.0)
    parser.add_argument("--high-buffer", type=float, default=10.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    trace = load_bandwidth_trace(args.trace)
    if args.controller == "static":
        config = ExperimentConfig(
            bitrates_kbps=args.bitrates,
            segment_duration_s=args.segment_duration,
            startup_buffer_s=args.startup_buffer,
            max_buffer_s=args.max_buffer,
            low_buffer_s=args.low_buffer,
            high_buffer_s=args.high_buffer,
            seed=args.seed,
        )
        rows, summary = run_static_experiment(trace, config, args.segments)
    else:
        if args.model is None:
            raise SystemExit("--model é obrigatório para --controller q-learning")
        agent, encoder, config, reward_config, _ = components_from_model(
            args.model,
            seed=args.seed,
        )
        rows, summary = run_q_learning_experiment(
            trace,
            config,
            agent,
            encoder,
            reward_config,
            args.segments,
        )
    csv_path, summary_path = save_results(rows, summary, args.output)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Log por segmento: {csv_path}")
    print(f"Resumo: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
