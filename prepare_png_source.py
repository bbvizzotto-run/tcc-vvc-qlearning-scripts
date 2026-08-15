"""CLI para obter e normalizar uma sequência pública de quadros PNG."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from png_source_preparation import (
    load_png_source_config,
    prepare_png_source,
    with_path_overrides,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Baixa somente os quadros PNG solicitados, valida e registra seus "
            "hashes e produz um trecho YUV normalizado com FFmpeg."
        )
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        help="sobrescreve source.cache_dir",
    )
    parser.add_argument("--output", type=Path, help="sobrescreve clip.output_yuv")
    parser.add_argument(
        "--provenance",
        type=Path,
        help="sobrescreve clip.provenance_path",
    )
    parser.add_argument("--ffmpeg", help="sobrescreve o executável FFmpeg")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="substitui conscientemente a saída YUV e a proveniência",
    )
    parser.add_argument(
        "--redownload",
        action="store_true",
        help="baixa novamente inclusive quadros válidos já presentes no cache",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = with_path_overrides(
        load_png_source_config(args.config),
        cache_dir=args.cache_dir,
        output_yuv=args.output,
        provenance_path=args.provenance,
        ffmpeg_executable=args.ffmpeg,
    )
    result = prepare_png_source(
        config,
        overwrite=args.overwrite,
        redownload=args.redownload,
        progress=lambda message: print(message, file=sys.stderr),
    )
    print(json.dumps(result["clip"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
