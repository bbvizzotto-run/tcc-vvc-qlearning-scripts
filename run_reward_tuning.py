"""Executa a seleção de pesos da recompensa exclusivamente em validação."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reward_tuning import (
    execute_reward_tuning,
    load_reward_tuning_definition,
    save_reward_tuning_result,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Seleciona pesos da recompensa em traces de validação sem executar "
            "os benchmarks finais."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("dvb_reward_tuning_config.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/dvb_reward_tuning"),
    )
    parser.add_argument(
        "--selected-protocol",
        type=Path,
        default=Path("dvb_uhd1_hfr_selected_protocol_config.json"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    definition = load_reward_tuning_definition(args.config)
    result = execute_reward_tuning(definition)
    paths = save_reward_tuning_result(
        definition,
        result,
        args.output_dir,
        args.selected_protocol,
    )
    selected = next(
        row for row in result.candidate_selection if row["selected"]
    )
    print(
        json.dumps(
            {
                "selected_candidate_id": result.selected_candidate_id,
                "selection_mode": result.selection_mode,
                "selected": selected,
                "evaluation_executed": False,
                "outputs": {key: str(value) for key, value in paths.items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
