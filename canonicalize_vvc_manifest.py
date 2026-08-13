"""CLI para canonicalizar rótulos de representações VVC medidas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from measured_ladder import canonicalize_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Separa o alvo do VVenC da taxa média medida usada como rótulo "
            "operacional da representação."
        )
    )
    parser.add_argument("--input", required=True, help="manifesto bruto medido")
    parser.add_argument(
        "--source-provenance",
        required=True,
        help="proveniência gerada pelo pipeline VVC",
    )
    parser.add_argument("--output", required=True, help="manifesto canônico")
    parser.add_argument(
        "--provenance",
        help="proveniência canônica; padrão: <output>.provenance.json",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="substitui conscientemente as saídas canônicas",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = canonicalize_manifest(
        source_manifest=Path(args.input),
        source_provenance=Path(args.source_provenance),
        output_manifest=Path(args.output),
        output_provenance=(Path(args.provenance) if args.provenance else None),
        overwrite=args.overwrite,
    )
    print(json.dumps(result["output"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
