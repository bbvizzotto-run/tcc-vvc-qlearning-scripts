"""Executa a comparação entre treinamento original e robusto."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from generalization_experiment import (
    execute_generalization_experiment,
    load_generalization_definition,
    save_generalization_result,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compara Q-Learning original e robusto com IC95%.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("generalization_config.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/generalization"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    definition = load_generalization_definition(args.config)
    result = execute_generalization_experiment(definition)
    paths = save_generalization_result(definition, result, args.output_dir)
    selected = [
        row
        for row in result.paired_differences
        if row["scope"] == "overall_per_seed"
        and row["comparison"] in {
            "robust_minus_standard",
            "robust_minus_static",
        }
    ]
    print(
        json.dumps(
            {
                "seeds": list(definition.standard_protocol.seeds),
                "training_runs": len(result.training_summary),
                "evaluation_runs": len(result.raw_runs),
                "overall_paired_differences": selected,
                "outputs": {key: str(value) for key, value in paths.items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
