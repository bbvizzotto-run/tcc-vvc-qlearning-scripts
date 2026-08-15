"""Executa uma única vez o protocolo confirmatório multicontéudo."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from multi_content_comparison import (
    FINAL_EXECUTION_POLICY,
    MultiContentComparisonDefinition,
    execute_multi_content_comparison,
    load_multi_content_comparison_definition,
    save_multi_content_comparison_result,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compara Q-Learning e quatro baselines em múltiplos conteúdos VVC."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("stage56_multicontent_comparison_config.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/stage56_multicontent_final"),
    )
    return parser


def prepare_final_execution(
    definition: MultiContentComparisonDefinition,
    output_dir: Path,
    config_path: Path,
) -> Path:
    """Cria uma trava persistente antes de carregar os traces de avaliação."""

    if definition.execution_policy != FINAL_EXECUTION_POLICY:
        raise ValueError("a execução requer a política final congelada")
    try:
        output_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise SystemExit(
            "execução recusada: o diretório da avaliação final já existe"
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
    definition = load_multi_content_comparison_definition(args.config)
    prepare_final_execution(definition, args.output_dir, args.config)
    result = execute_multi_content_comparison(definition, progress=print)
    paths = save_multi_content_comparison_result(
        definition, result, args.output_dir
    )
    overall = [
        row
        for row in result.paired_differences
        if row["scope"] == "overall_content_balanced_per_seed"
        and row["metric"] == definition.primary_contrast["metric"]
        and row["baseline"] == definition.primary_contrast["baseline"]
    ]
    print(
        json.dumps(
            {
                "stage": definition.stage,
                "contents": [item.content_id for item in definition.contents],
                "seeds": list(definition.seeds),
                "evaluation_runs": len(result.raw_runs),
                "overall_primary_paired_differences": overall,
                "outputs": {key: str(value) for key, value in paths.items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
