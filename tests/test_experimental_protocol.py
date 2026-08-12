import json
import tempfile
import unittest
from pathlib import Path

from experiment import ExperimentConfig
from experimental_protocol import (
    ProtocolDefinition,
    confidence_interval_95,
    execute_protocol,
    save_protocol_result,
)
from q_learning_pipeline import RewardConfig, TrainingConfig


class ExperimentalProtocolTest(unittest.TestCase):
    def test_student_confidence_interval(self):
        interval = confidence_interval_95([1, 2, 3, 4, 5])

        self.assertEqual(interval["n"], 5)
        self.assertEqual(interval["mean"], 3)
        self.assertAlmostEqual(interval["std"], 1.5811388300841898)
        self.assertAlmostEqual(interval["ci95_half_width"], 1.9629284245738559)

    def test_protocol_is_reproducible_and_persists_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            train_path = root / "train.csv"
            eval_a_path = root / "eval_a.csv"
            eval_b_path = root / "eval_b.csv"
            train_path.write_text(
                "segment,bandwidth_kbps\n0,3000\n1,2000\n2,700\n3,1500\n",
                encoding="utf-8",
            )
            eval_a_path.write_text(
                "segment,bandwidth_kbps\n0,2500\n1,800\n2,500\n3,2000\n",
                encoding="utf-8",
            )
            eval_b_path.write_text(
                "segment,bandwidth_kbps\n0,1000\n1,3000\n2,600\n3,2500\n",
                encoding="utf-8",
            )
            definition = ProtocolDefinition(
                source_path=root / "protocol.json",
                protocol_version=1,
                confidence_level=0.95,
                seeds=(3, 7),
                training_trace_paths=(train_path,),
                evaluation_trace_paths=(eval_a_path, eval_b_path),
                experiment_config=ExperimentConfig(
                    bitrates_kbps=(500, 1000, 2000),
                    segment_duration_s=2,
                    startup_buffer_s=2,
                    max_buffer_s=10,
                    seed=3,
                ),
                training_config=TrainingConfig(
                    episodes=20,
                    epsilon_decay=0.9,
                    epsilon_min=0.05,
                    buffer_boundaries_s=(2, 4, 8),
                    seed=3,
                ),
                reward_config=RewardConfig(target_buffer_s=4),
            )

            first = execute_protocol(definition)
            second = execute_protocol(definition)
            self.assertEqual(first.raw_runs, second.raw_runs)
            self.assertEqual(len(first.raw_runs), 8)
            self.assertEqual(len(first.aggregate), 36)
            self.assertEqual(len(first.paired_differences), 18)

            paths = save_protocol_result(definition, first, root / "output")
            self.assertTrue(all(path.is_file() for path in paths.values()))
            self.assertTrue(
                (root / "output/models/q_learning_seed_3.npz").is_file()
            )
            with paths["manifest"].open(encoding="utf-8") as handle:
                manifest = json.load(handle)
            self.assertEqual(manifest["seeds"], [3, 7])
            self.assertEqual(
                manifest["delta_definition"],
                "q-learning_minus_static",
            )


if __name__ == "__main__":
    unittest.main()
