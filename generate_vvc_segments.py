"""CLI para gerar segmentos VVC, medições e manifesto experimental."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from vvc_segment_pipeline import (
    build_dry_run_plan,
    execute_pipeline,
    load_pipeline_config,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Codifica uma matriz segmento × bitrate com VVenC e gera o manifesto "
            "aceito pelo simulador"
        )
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="valida a configuração e exibe os comandos sem executar ferramentas",
    )
    existing_mode = parser.add_mutually_exclusive_group()
    existing_mode.add_argument(
        "--overwrite",
        action="store_true",
        help="permite substituir somente os artefatos determinísticos desta configuração",
    )
    existing_mode.add_argument(
        "--resume",
        action="store_true",
        help="reutiliza bitstreams parciais somente quando o comando salvo coincide",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_pipeline_config(args.config)
    result = (
        build_dry_run_plan(config)
        if args.dry_run
        else execute_pipeline(
            config,
            overwrite=args.overwrite,
            resume=args.resume,
            progress=lambda message: print(message, file=sys.stderr),
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
