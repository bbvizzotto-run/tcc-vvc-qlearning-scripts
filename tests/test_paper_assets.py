import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from paper_assets import (
    build_and_write_tables,
    build_primary_contrast_table,
    load_paper_config,
    read_csv_rows,
    validate_frozen_inputs,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "paper/paper_config.json"
RESULTS = ROOT / "results/stage56_multicontent_final"


class PaperAssetsTest(unittest.TestCase):
    def setUp(self):
        self.config = load_paper_config(CONFIG_PATH)

    def test_every_paper_input_is_sha256_pinned(self):
        validate_frozen_inputs(ROOT, self.config)
        self.assertEqual(len(self.config["frozen_inputs_sha256"]), 9)
        self.assertEqual(
            self.config["frozen_results_commit"],
            "efc5aa3be155e5533cd16f17fc76354a73ae46c7",
        )

    def test_primary_table_matches_preregistered_result(self):
        paired = read_csv_rows(RESULTS / "paired_differences.csv")
        rows = build_primary_contrast_table(paired)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["Scope"], "Overall")
        self.assertEqual(rows[0]["QL - RobustMPC"], "-0.675")
        self.assertEqual(rows[0]["95% CI"], "[-0.774, -0.577]")
        self.assertTrue(
            all(row["Favored controller"] == "RobustMPC" for row in rows)
        )

    def test_tables_are_generated_in_three_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            generated = build_and_write_tables(ROOT, self.config, Path(tmp))
            self.assertEqual(len(generated), 15)
            self.assertTrue(all(path.is_file() for path in generated))
            table = Path(tmp) / "tables/table_03_controller_results.csv"
            with table.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 5)
            robust = next(row for row in rows if row["Controller"] == "RobustMPC")
            qlearning = next(row for row in rows if row["Controller"] == "Q-Learning")
            self.assertGreater(
                float(robust["Objective reward"]), float(qlearning["Objective reward"])
            )

    def test_checked_in_generated_assets_match_manifest(self):
        path = ROOT / "paper/generated/asset_manifest.json"
        if not path.is_file():
            self.skipTest("generated paper assets have not been built")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["paper_title"], self.config["paper_title"])
        self.assertEqual(len(manifest["generated_assets"]), 29)
        for relative, expected in manifest["generated_assets"].items():
            asset = path.parent / relative
            actual = hashlib.sha256(asset.read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)


if __name__ == "__main__":
    unittest.main()
