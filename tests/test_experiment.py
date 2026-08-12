import csv
import json
import tempfile
import unittest
from pathlib import Path

from experiment import ExperimentConfig, load_bandwidth_trace, run_static_experiment, save_results


class ExperimentTest(unittest.TestCase):
    def test_run_and_save_are_reproducible(self):
        config = ExperimentConfig(
            bitrates_kbps=(500, 1000),
            segment_duration_s=2,
            startup_buffer_s=2,
            max_buffer_s=8,
            low_buffer_s=2,
            high_buffer_s=4,
            seed=7,
        )
        rows, summary = run_static_experiment([2000] * 5, config)

        self.assertEqual(len(rows), 5)
        self.assertEqual(summary["segments"], 5)
        self.assertEqual(summary["controller"], "static")

        with tempfile.TemporaryDirectory() as tmp:
            csv_path, summary_path = save_results(rows, summary, Path(tmp) / "run.csv")
            with csv_path.open(newline="", encoding="utf-8") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 5)
            with summary_path.open(encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["seed"], 7)

    def test_load_trace(self):
        values = load_bandwidth_trace("bandwidth_traces/stable.csv")
        self.assertEqual(len(values), 20)
        self.assertTrue(all(value == 5000 for value in values))


if __name__ == "__main__":
    unittest.main()
