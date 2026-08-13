"""Executa a comparação da etapa 5.4a."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from abr_comparison import (
    execute_abr_comparison,
    load_abr_comparison_definition,
    save_abr_comparison_result,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compara Q-Learning, throughput, BOLA-BASIC e RobustMPC.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("dvb_abr_comparison_config.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/dvb_abr_comparison"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    definition = load_abr_comparison_definition(args.config)
    result = execute_abr_comparison(definition)
    paths = save_abr_comparison_result(definition, result, args.output_dir)
    overall = [
        row
        for row in result.paired_differences
        if row["scope"] == "overall_per_seed"
    ]
    print(
        json.dumps(
            {
                "stage": "5.4a",
                "seeds": list(definition.base_protocol.seeds),
                "evaluation_runs": len(result.raw_runs),
                "overall_paired_differences": overall,
                "outputs": {key: str(value) for key, value in paths.items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
