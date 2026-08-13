"""CLI para extrair de forma auditável um trecho de uma fonte Y4M/XZ."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from y4m_source_preparation import (
    load_source_preparation_config,
    prepare_source,
    with_path_overrides,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Valida um arquivo Y4M/XZ e envia seu fluxo descomprimido ao "
            "FFmpeg, gravando somente o trecho YUV solicitado."
        )
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--input", type=Path, help="sobrescreve source.input_xz")
    parser.add_argument("--output", type=Path, help="sobrescreve clip.output_yuv")
    parser.add_argument(
        "--provenance",
        type=Path,
        help="sobrescreve clip.provenance_path",
    )
    parser.add_argument(
        "--ffmpeg",
        help="sobrescreve o executável FFmpeg configurado",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="substitui conscientemente a saída e a proveniência",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = with_path_overrides(
        load_source_preparation_config(args.config),
        input_xz=args.input,
        output_yuv=args.output,
        provenance_path=args.provenance,
        ffmpeg_executable=args.ffmpeg,
    )
    result = prepare_source(
        config,
        overwrite=args.overwrite,
        progress=lambda message: print(message, file=sys.stderr),
    )
    print(json.dumps(result["clip"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
