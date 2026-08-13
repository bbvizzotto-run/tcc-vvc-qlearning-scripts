"""CLI para gerar os traces independentes da Etapa 5.4b."""

from __future__ import annotations

import argparse
from pathlib import Path

from trace_synthesis import (
    generate_trace_suite,
    load_trace_synthesis_definition,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gera traces de validação e holdout reproduzíveis.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("stage54b_trace_synthesis_config.json"),
    )
    parser.add_argument(
        "--provenance",
        type=Path,
        default=Path("bandwidth_traces/stage54b_trace_provenance.json"),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    definition = load_trace_synthesis_definition(args.config)
    outputs = generate_trace_suite(
        definition,
        args.provenance,
        overwrite=args.overwrite,
    )
    for trace_id, path in outputs.items():
        print(f"{trace_id}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
