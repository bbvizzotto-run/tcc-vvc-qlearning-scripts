"""Treina e persiste o controlador Q-Learning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import fmean

from experiment import ExperimentConfig, load_bandwidth_trace
from q_learning_pipeline import (
    RewardConfig,
    TrainingConfig,
    save_training_history,
    train_q_learning,
)
from run_experiment import parse_bitrates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Treina o agente Q-Learning no simulador segmentado.",
    )
    parser.add_argument(
        "--trace",
        action="append",
        type=Path,
        required=True,
        help="trace de treinamento; repita o argumento para usar vários",
    )
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--episodes", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bitrates", type=parse_bitrates, default=(500, 1000, 2000, 4000))
    parser.add_argument("--segment-duration", type=float, default=2.0)
    parser.add_argument("--startup-buffer", type=float, default=4.0)
    parser.add_argument("--max-buffer", type=float, default=20.0)
    parser.add_argument("--learning-rate", type=float, default=0.1)
    parser.add_argument("--discount-factor", type=float, default=0.95)
    parser.add_argument("--epsilon-start", type=float, default=1.0)
    parser.add_argument("--epsilon-min", type=float, default=0.05)
    parser.add_argument("--epsilon-decay", type=float, default=0.995)
    parser.add_argument("--quality-weight", type=float, default=1.0)
    parser.add_argument("--rebuffering-weight", type=float, default=10.0)
    parser.add_argument("--switch-weight", type=float, default=0.25)
    parser.add_argument("--low-buffer-weight", type=float, default=1.0)
    parser.add_argument("--target-buffer", type=float, default=8.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    experiment_config = ExperimentConfig(
        bitrates_kbps=args.bitrates,
        segment_duration_s=args.segment_duration,
        startup_buffer_s=args.startup_buffer,
        max_buffer_s=args.max_buffer,
        seed=args.seed,
    )
    training_config = TrainingConfig(
        episodes=args.episodes,
        learning_rate=args.learning_rate,
        discount_factor=args.discount_factor,
        epsilon_start=args.epsilon_start,
        epsilon_min=args.epsilon_min,
        epsilon_decay=args.epsilon_decay,
        seed=args.seed,
    )
    reward_config = RewardConfig(
        quality_weight=args.quality_weight,
        rebuffering_weight=args.rebuffering_weight,
        switch_weight=args.switch_weight,
        low_buffer_weight=args.low_buffer_weight,
        target_buffer_s=args.target_buffer,
    )
    named_traces = [
        (path.stem, load_bandwidth_trace(path))
        for path in args.trace
    ]
    agent, _, history, metadata = train_q_learning(
        named_traces,
        experiment_config,
        training_config,
        reward_config,
    )
    model_path = agent.save(args.model, metadata)
    history_path = save_training_history(history, args.history)
    last_window = history[-min(50, len(history)) :]
    summary = {
        "episodes": len(history),
        "final_epsilon": agent.epsilon,
        "mean_reward_last_window": fmean(
            float(row["mean_reward"]) for row in last_window
        ),
        "mean_rebuffering_last_window_s": fmean(
            float(row["rebuffering_s"]) for row in last_window
        ),
        "visited_states": int((abs(agent.q_table).sum(axis=1) > 0).sum()),
        "total_states": agent.state_space_size,
        "model": str(model_path),
        "history": str(history_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
