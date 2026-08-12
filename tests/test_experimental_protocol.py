import json
import tempfile
import unittest
from pathlib import Path

from experiment import ExperimentConfig
from experimental_protocol import (
    ProtocolDefinition,
    confidence_interval_95,
    execute_protocol,
    load_protocol_definition,
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

    def test_loads_optional_segment_manifest_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trace = root / "trace.csv"
            manifest = root / "segments.csv"
            config = root / "protocol.json"
            trace.write_text(
                "segment,bandwidth_kbps\n0,1000\n",
                encoding="utf-8",
            )
            manifest.write_text(
                "sequence,segment,bitrate_kbps,duration_s,size_bytes\n"
                "video,0,500,2,125000\n",
                encoding="utf-8",
            )
            config.write_text(
                json.dumps(
                    {
                        "protocol_version": 1,
                        "seeds": [1, 2],
                        "training_traces": ["trace.csv"],
                        "evaluation_traces": ["trace.csv"],
                        "segment_manifest": "segments.csv",
                        "experiment_config": {"bitrates_kbps": [500]},
                        "training_config": {
                            "episodes": 1,
                            "buffer_boundaries_s": [2],
                        },
                        "reward_config": {},
                    }
                ),
                encoding="utf-8",
            )

            definition = load_protocol_definition(config)

        self.assertEqual(definition.segment_manifest_path, manifest.resolve())

    def test_protocol_is_reproducible_and_persists_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            train_path = root / "train.csv"
            eval_a_path = root / "eval_a.csv"
            eval_b_path = root / "eval_b.csv"
            segment_manifest_path = root / "segments.csv"
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
            segment_manifest_path.write_text(
                "sequence,segment,bitrate_kbps,duration_s,size_bytes\n"
                "video,0,500,2,120000\n"
                "video,0,1000,2,240000\n"
                "video,0,2000,2,480000\n"
                "video,1,500,2,140000\n"
                "video,1,1000,2,280000\n"
                "video,1,2000,2,560000\n"
                "video,2,500,2,110000\n"
                "video,2,1000,2,220000\n"
                "video,2,2000,2,440000\n"
                "video,3,500,2,130000\n"
                "video,3,1000,2,260000\n"
                "video,3,2000,2,520000\n",
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
                segment_manifest_path=segment_manifest_path,
            )

            first = execute_protocol(definition)
            second = execute_protocol(definition)
            self.assertEqual(first.raw_runs, second.raw_runs)
            self.assertEqual(len(first.raw_runs), 8)
            self.assertEqual(len(first.aggregate), 42)
            self.assertEqual(len(first.paired_differences), 21)
            self.assertIn("average_payload_bitrate_kbps", first.metrics)

            paths = save_protocol_result(definition, first, root / "output")
            self.assertTrue(all(path.is_file() for path in paths.values()))
            self.assertTrue(
                (root / "output/models/q_learning_seed_3.npz").is_file()
            )
            with paths["manifest"].open(encoding="utf-8") as handle:
                manifest = json.load(handle)
            self.assertEqual(manifest["seeds"], [3, 7])
            self.assertEqual(manifest["segment_manifest"]["sequence"], "video")
            self.assertEqual(
                manifest["segment_manifest"]["segment_count"],
                4,
            )
            self.assertEqual(
                manifest["delta_definition"],
                "q-learning_minus_static",
            )


if __name__ == "__main__":
    unittest.main()
