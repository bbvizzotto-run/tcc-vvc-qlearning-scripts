import json
import tempfile
import unittest
from pathlib import Path

from abr_baselines import BolaConfig, RobustMpcConfig, ThroughputConfig
from multi_content_comparison import (
    FINAL_EXECUTION_POLICY,
    PARAMETER_POLICY,
    ContentInput,
    ExperimentTemplate,
    MultiContentComparisonDefinition,
    TraceInput,
    execute_multi_content_comparison,
    load_multi_content_comparison_definition,
    save_multi_content_comparison_result,
)
from q_learning_pipeline import RewardConfig, TrainingConfig
from run_multi_content_comparison import prepare_final_execution


ROOT = Path(__file__).resolve().parents[1]


class MultiContentComparisonTest(unittest.TestCase):
    def _write_manifest(self, path: Path, sequence: str, offset: int) -> None:
        rows = [
            "sequence,segment,bitrate_kbps,duration_s,size_bytes,psnr_y_db"
        ]
        for segment in range(4):
            rows.extend(
                [
                    f"{sequence},{segment},500,1,{62500 + offset + segment},35.0",
                    f"{sequence},{segment},2000,1,{250000 + offset + segment},42.0",
                ]
            )
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    def _fixture(self, root: Path) -> MultiContentComparisonDefinition:
        train = root / "train.csv"
        evaluation_a = root / "evaluation_a.csv"
        evaluation_b = root / "evaluation_b.csv"
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
        first_manifest = root / "first.csv"
        second_manifest = root / "second.csv"
        self._write_manifest(first_manifest, "first", 0)
        self._write_manifest(second_manifest, "second", 1000)
        config_path = root / "comparison.json"
        config_path.write_text("{}\n", encoding="utf-8")
        return MultiContentComparisonDefinition(
            source_path=config_path,
            comparison_version=1,
            stage="test",
            study_status="test",
            parameter_policy=PARAMETER_POLICY,
            execution_policy=FINAL_EXECUTION_POLICY,
            previous_holdout_status="not_executed",
            confidence_level=0.95,
            seeds=(3, 7),
            training_traces=(TraceInput("train", train),),
            evaluation_traces=(
                TraceInput("evaluation_a", evaluation_a),
                TraceInput("evaluation_b", evaluation_b),
            ),
            contents=(
                ContentInput("first", first_manifest),
                ContentInput("second", second_manifest),
            ),
            expected_segments=4,
            expected_representations=2,
            experiment_template=ExperimentTemplate(
                segment_duration_s=1,
                startup_buffer_s=2,
                max_buffer_s=8,
                low_buffer_s=2,
                high_buffer_s=6,
            ),
            training_config=TrainingConfig(
                episodes=8,
                epsilon_decay=0.8,
                epsilon_min=0.05,
                buffer_boundaries_s=(2, 4, 6),
                seed=3,
                startup_guard=True,
            ),
            reward_config=RewardConfig(
                low_buffer_weight=2,
                startup_weight=0.5,
                target_buffer_s=4,
            ),
            throughput_config=ThroughputConfig(
                history_window=2, safety_factor=0.85
            ),
            bola_config=BolaConfig(
                minimum_buffer_s=2, buffer_target_s=8
            ),
            robust_mpc_config=RobustMpcConfig(
                horizon=2, history_window=2, error_window=2
            ),
            primary_metrics=("mean_objective_reward",),
            secondary_metrics=(
                "startup_delay_s",
                "rebuffering_s",
                "rebuffering_rate_percent",
                "average_bitrate_kbps",
                "average_payload_bitrate_kbps",
                "buffer_mean_s",
                "buffer_std_s",
                "mean_quality_utility",
                "mean_psnr_y_db",
                "switch_count",
                "high_representation_fraction_percent",
            ),
            primary_contrast={
                "scope": "overall_content_balanced_per_seed",
                "baseline": "robust-mpc",
                "metric": "mean_objective_reward",
                "alternative": "two_sided",
            },
            references={},
        )

    def test_execution_is_reproducible_balanced_and_auditable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            definition = self._fixture(root)
            first = execute_multi_content_comparison(definition)
            second = execute_multi_content_comparison(definition)

            self.assertEqual(first.raw_runs, second.raw_runs)
            self.assertEqual(len(first.raw_runs), 40)
            self.assertEqual(len(first.aggregate), 420)
            self.assertEqual(len(first.paired_differences), 336)
            self.assertEqual(len(first.training_summary), 4)
            self.assertEqual(
                {row["content"] for row in first.raw_runs},
                {"first", "second"},
            )
            self.assertTrue(
                all(float(row["mean_psnr_y_db"]) > 0 for row in first.raw_runs)
            )

            paths = save_multi_content_comparison_result(
                definition, first, root / "output"
            )
            self.assertTrue(all(path.is_file() for path in paths.values()))
            persisted = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            self.assertEqual(persisted["statistical_unit"], "training_seed")
            self.assertEqual(
                persisted["primary_contrast"]["baseline"], "robust-mpc"
            )
            self.assertIn("raw_runs", persisted["artifacts"])

    def test_loader_freezes_the_real_protocol_without_loading_trace_values(self):
        definition = load_multi_content_comparison_definition(
            ROOT / "stage56_multicontent_comparison_config.json"
        )
        self.assertEqual(len(definition.contents), 4)
        self.assertEqual(len(definition.seeds), 10)
        self.assertEqual(len(definition.evaluation_traces), 3)
        self.assertEqual(definition.expected_segments, 60)
        self.assertTrue(definition.training_config.startup_guard)
        self.assertEqual(definition.reward_config.startup_weight, 0.5)
        self.assertTrue(
            all(
                trace.bandwidth_scale == 1.0
                for trace in definition.evaluation_traces
            )
        )
        self.assertEqual(
            definition.primary_contrast,
            {
                "scope": "overall_content_balanced_per_seed",
                "baseline": "robust-mpc",
                "metric": "mean_objective_reward",
                "alternative": "two_sided",
            },
        )

    def test_final_execution_refuses_an_existing_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            definition = self._fixture(root)
            output = root / "final"
            marker = prepare_final_execution(
                definition, output, definition.source_path
            )
            self.assertEqual(marker, output / ".execution_started.json")
            self.assertTrue(marker.is_file())
            with self.assertRaisesRegex(SystemExit, "já existe"):
                prepare_final_execution(
                    definition, output, definition.source_path
                )


if __name__ == "__main__":
    unittest.main()
