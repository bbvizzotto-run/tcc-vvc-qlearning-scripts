import json
import tempfile
import unittest
from pathlib import Path

from abr_baselines import BolaConfig, RobustMpcConfig, ThroughputConfig
from abr_comparison import (
    AbrComparisonDefinition,
    execute_abr_comparison,
    load_abr_comparison_definition,
    save_abr_comparison_result,
)
from experiment import ExperimentConfig
from experimental_protocol import ProtocolDefinition
from q_learning_pipeline import RewardConfig, TrainingConfig


class AbrComparisonTest(unittest.TestCase):
    def _fixture(self, root: Path) -> AbrComparisonDefinition:
        train = root / "train.csv"
        evaluation_a = root / "evaluation_a.csv"
        evaluation_b = root / "evaluation_b.csv"
        manifest = root / "segments.csv"
        protocol_path = root / "protocol.json"
        comparison_path = root / "comparison.json"
        train.write_text(
            "segment,bandwidth_kbps\n0,3000\n1,800\n2,2500\n3,1000\n",
            encoding="utf-8",
        )
        evaluation_a.write_text(
            "segment,bandwidth_kbps\n0,2000\n1,700\n2,3000\n3,900\n",
            encoding="utf-8",
        )
        evaluation_b.write_text(
            "segment,bandwidth_kbps\n0,1000\n1,2500\n2,800\n3,3000\n",
            encoding="utf-8",
        )
        rows = ["sequence,segment,bitrate_kbps,duration_s,size_bytes"]
        for segment in range(4):
            rows.extend(
                [
                    f"video,{segment},500,2,{125000 + segment * 1000}",
                    f"video,{segment},2000,2,{500000 + segment * 4000}",
                ]
            )
        manifest.write_text("\n".join(rows) + "\n", encoding="utf-8")
        protocol_path.write_text("{}\n", encoding="utf-8")
        comparison_path.write_text("{}\n", encoding="utf-8")
        protocol = ProtocolDefinition(
            source_path=protocol_path,
            protocol_version=2,
            confidence_level=0.95,
            seeds=(3, 7),
            training_trace_paths=(train,),
            evaluation_trace_paths=(evaluation_a, evaluation_b),
            experiment_config=ExperimentConfig(
                bitrates_kbps=(500, 2000),
                segment_duration_s=2,
                startup_buffer_s=2,
                max_buffer_s=10,
                seed=3,
            ),
            training_config=TrainingConfig(
                episodes=10,
                epsilon_decay=0.8,
                epsilon_min=0.05,
                buffer_boundaries_s=(2, 4, 8),
                seed=3,
            ),
            reward_config=RewardConfig(target_buffer_s=4),
            segment_manifest_path=manifest,
        )
        return AbrComparisonDefinition(
            source_path=comparison_path,
            comparison_version=1,
            base_protocol=protocol,
            throughput_config=ThroughputConfig(history_window=2, safety_factor=0.85),
            bola_config=BolaConfig(minimum_buffer_s=2, buffer_target_s=10),
            robust_mpc_config=RobustMpcConfig(horizon=2),
            parameter_policy="frozen_before_first_execution_no_evaluation_tuning",
            study_status="test",
            references={},
        )

    def test_comparison_is_reproducible_and_persists_auditable_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            definition = self._fixture(root)
            first = execute_abr_comparison(definition)
            second = execute_abr_comparison(definition)

            self.assertEqual(first.raw_runs, second.raw_runs)
            self.assertEqual(len(first.raw_runs), 20)
            self.assertEqual(len(first.aggregate), 150)
            self.assertEqual(len(first.paired_differences), 120)
            self.assertEqual(
                {row["controller"] for row in first.raw_runs},
                {"static", "throughput", "bola-basic", "robust-mpc", "q-learning"},
            )
            paths = save_abr_comparison_result(definition, first, root / "output")
            self.assertTrue(all(path.is_file() for path in paths.values()))
            with paths["manifest"].open(encoding="utf-8") as handle:
                persisted = json.load(handle)
            self.assertEqual(persisted["stage"], "5.4a")
            self.assertIn("raw_runs", persisted["artifacts"])
            self.assertIn("q-learning_minus_robust-mpc", persisted["delta_definitions"])

    def test_loader_requires_explicit_frozen_parameter_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trace = root / "trace.csv"
            manifest = root / "segments.csv"
            protocol = root / "protocol.json"
            comparison = root / "comparison.json"
            trace.write_text(
                "segment,bandwidth_kbps\n0,1000\n",
                encoding="utf-8",
            )
            manifest.write_text(
                "sequence,segment,bitrate_kbps,duration_s,size_bytes\n"
                "video,0,500,2,125000\n",
                encoding="utf-8",
            )
            protocol.write_text(
                json.dumps(
                    {
                        "protocol_version": 2,
                        "seeds": [1, 2],
                        "training_traces": ["trace.csv"],
                        "evaluation_traces": ["trace.csv"],
                        "experiment_config": {"bitrates_kbps": [500]},
                        "training_config": {
                            "episodes": 1,
                            "buffer_boundaries_s": [2],
                        },
                        "reward_config": {},
                        "segment_manifest": "segments.csv",
                    }
                ),
                encoding="utf-8",
            )
            comparison.write_text(
                json.dumps(
                    {
                        "comparison_version": 1,
                        "base_protocol": "protocol.json",
                        "parameter_policy": "tune_on_evaluation",
                        "study_status": "test",
                        "throughput": {},
                        "bola_basic": {},
                        "robust_mpc": {},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "congelar parâmetros"):
                load_abr_comparison_definition(comparison)


if __name__ == "__main__":
    unittest.main()
