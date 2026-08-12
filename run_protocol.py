"""Executa o protocolo experimental multi-semente."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from experimental_protocol import (
    execute_protocol,
    load_protocol_definition,
    save_protocol_result,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Executa treinamento repetido e análise com IC95%.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("protocol_config.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/protocol"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    definition = load_protocol_definition(args.config)
    result = execute_protocol(definition)
    paths = save_protocol_result(definition, result, args.output_dir)
    overall_differences = [
        row
        for row in result.paired_differences
        if row["scope"] == "overall_per_seed"
    ]
    print(
        json.dumps(
            {
                "seeds": list(definition.seeds),
                "training_runs": len(result.training_summary),
                "evaluation_runs": len(result.raw_runs),
                "overall_paired_differences": overall_differences,
                "outputs": {key: str(value) for key, value in paths.items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
