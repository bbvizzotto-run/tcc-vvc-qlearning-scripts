"""Executa uma comparação pareada entre controladores ABR."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from abr_comparison import (
    AbrComparisonDefinition,
    execute_abr_comparison,
    load_abr_comparison_definition,
    save_abr_comparison_result,
)


FINAL_HOLDOUT_POLICY = "single_final_execution_after_versioned_freeze"


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


def prepare_final_holdout_execution(
    definition: AbrComparisonDefinition,
    output_dir: Path,
    config_path: Path,
) -> Path | None:
    """Cria uma trava persistente antes de a execução única carregar o holdout."""

    if definition.execution_policy != FINAL_HOLDOUT_POLICY:
        return None
    try:
        output_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise SystemExit(
            "execução recusada: o diretório do holdout já existe"
        ) from error
    marker_path = output_dir / ".execution_started.json"
    marker = {
        "stage": definition.stage,
        "status": "execution_started",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": str(config_path),
        "output_dir": str(output_dir),
        "execution_policy": definition.execution_policy,
    }
    with marker_path.open("x", encoding="utf-8") as handle:
        json.dump(marker, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return marker_path


def main() -> int:
    args = build_parser().parse_args()
    definition = load_abr_comparison_definition(args.config)
    prepare_final_holdout_execution(definition, args.output_dir, args.config)
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
                "stage": definition.stage,
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
