import csv
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/stage56_multicontent_final"


def _rows(name: str) -> list[dict[str, str]]:
    with (RESULTS / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class Stage56ResultsIntegrationTest(unittest.TestCase):
    def test_final_matrix_is_complete_and_has_unique_run_keys(self):
        raw = _rows("raw_runs.csv")
        aggregate = _rows("aggregate.csv")
        paired = _rows("paired_differences.csv")
        training = _rows("training_summary.csv")

        self.assertEqual(len(raw), 600)
        self.assertEqual(len(aggregate), 1020)
        self.assertEqual(len(paired), 816)
        self.assertEqual(len(training), 40)
        keys = {
            (
                row["content"],
                row["training_seed"],
                row["trace"],
                row["controller"],
            )
            for row in raw
        }
        self.assertEqual(len(keys), 600)

    def test_primary_result_matches_the_frozen_contrast(self):
        config = json.loads(
            (ROOT / "stage56_multicontent_comparison_config.json").read_text(
                encoding="utf-8"
            )
        )
        rows = [
            row
            for row in _rows("paired_differences.csv")
            if row["scope"] == config["primary_contrast"]["scope"]
            and row["baseline"] == config["primary_contrast"]["baseline"]
            and row["metric"] == config["primary_contrast"]["metric"]
        ]
        self.assertEqual(len(rows), 1)
        primary = rows[0]
        self.assertAlmostEqual(float(primary["mean"]), -0.6753627866836374)
        self.assertAlmostEqual(float(primary["ci95_low"]), -0.7737822114630142)
        self.assertAlmostEqual(float(primary["ci95_high"]), -0.5769433619042605)
        self.assertLess(float(primary["ci95_high"]), 0)
        self.assertEqual(primary["ci95_excludes_zero"], "True")

        per_content = [
            row
            for row in _rows("paired_differences.csv")
            if row["scope"] == "per_content_per_seed"
            and row["baseline"] == "robust-mpc"
            and row["metric"] == "mean_objective_reward"
        ]
        self.assertEqual(len(per_content), 4)
        self.assertTrue(all(float(row["ci95_high"]) < 0 for row in per_content))

    def test_execution_attestation_pins_every_reported_artifact(self):
        attestation = json.loads(
            (RESULTS / "execution_attestation.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(attestation["execution_count"], 1)
        self.assertFalse(attestation["rerun_performed"])
        self.assertFalse(attestation["post_freeze_parameter_changes"])
        for name, expected in attestation["artifacts_sha256"].items():
            path = (
                ROOT / name
                if name == "stage56_pre_execution_attestation.json"
                else RESULTS / name
            )
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(actual, expected, name)

    def test_result_manifest_pins_machine_readable_outputs(self):
        manifest = json.loads(
            (RESULTS / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["statistical_unit"], "training_seed")
        self.assertEqual(
            manifest["primary_contrast"],
            {
                "alternative": "two_sided",
                "baseline": "robust-mpc",
                "metric": "mean_objective_reward",
                "scope": "overall_content_balanced_per_seed",
            },
        )
        for item in manifest["artifacts"].values():
            path = RESULTS / item["path"]
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(actual, item["sha256"], item["path"])


if __name__ == "__main__":
    unittest.main()
