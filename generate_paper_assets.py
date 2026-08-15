"""Command-line entry point for the Stage 5.7a publication assets."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from paper_assets import generate_all


ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate frozen tables and figures for the VVC ABR paper."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "paper/paper_config.json",
        help="paper asset configuration (default: paper/paper_config.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="optional output directory; defaults to the configured paper/generated",
    )
    args = parser.parse_args()
    os.environ.setdefault(
        "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "tcc-vvc-matplotlib")
    )
    manifest = generate_all(ROOT, args.config.resolve(), args.output_dir)
    configured_output = load_output_path(args.config.resolve())
    print(
        json.dumps(
            {
                "paper_title": manifest["paper_title"],
                "generated_assets": len(manifest["generated_assets"]),
                "output_directory": str(
                    (args.output_dir or ROOT / configured_output).resolve()
                ),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def load_output_path(config_path: Path) -> Path:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    return Path(config["output_directory"])


if __name__ == "__main__":
    raise SystemExit(main())
