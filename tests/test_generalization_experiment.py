import json
import tempfile
import unittest
from pathlib import Path

from experiment import ExperimentConfig
from experimental_protocol import ProtocolDefinition
from generalization_experiment import (
    GeneralizationDefinition,
    execute_generalization_experiment,
    save_generalization_result,
)
from q_learning_pipeline import RewardConfig, TrainingConfig
from trace_augmentation import TraceAugmentationConfig


class GeneralizationExperimentTest(unittest.TestCase):
    def test_comparison_is_reproducible_and_persists_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            train = root / "train.csv"
            validation = root / "validation.csv"
            evaluation = root / "evaluation.csv"
            train.write_text(
                "segment,bandwidth_kbps\n0,3000\n1,2200\n2,900\n3,1800\n",
                encoding="utf-8",
            )
            validation.write_text(
                "segment,bandwidth_kbps\n0,2800\n1,500\n2,2400\n3,700\n",
                encoding="utf-8",
            )
            evaluation.write_text(
                "segment,bandwidth_kbps\n0,2500\n1,600\n2,400\n3,2600\n",
                encoding="utf-8",
            )
            experiment = ExperimentConfig(
                bitrates_kbps=(500, 1000, 2000),
                segment_duration_s=2,
                startup_buffer_s=2,
                max_buffer_s=10,
                seed=3,
            )
            training = TrainingConfig(
                episodes=20,
                epsilon_decay=0.9,
                epsilon_min=0.05,
                buffer_boundaries_s=(2, 4, 8),
                seed=3,
            )
            reward = RewardConfig(target_buffer_s=4)
            standard = ProtocolDefinition(
                source_path=root / "standard.json",
                protocol_version=1,
                confidence_level=0.95,
                seeds=(3, 7),
                training_trace_paths=(train,),
                evaluation_trace_paths=(evaluation,),
                experiment_config=experiment,
                training_config=training,
                reward_config=reward,
            )
            robust = ProtocolDefinition(
                source_path=root / "robust.json",
                protocol_version=2,
                confidence_level=0.95,
                seeds=(3, 7),
                training_trace_paths=(train,),
                evaluation_trace_paths=(evaluation,),
                experiment_config=experiment,
                training_config=training,
                reward_config=reward,
                trace_augmentation=TraceAugmentationConfig(),
            )
            definition = GeneralizationDefinition(
                source_path=root / "generalization.json",
                experiment_version=1,
                standard_protocol=standard,
                robust_protocol=robust,
                validation_trace_paths=(validation,),
            )

            first = execute_generalization_experiment(definition)
            second = execute_generalization_experiment(definition)

            self.assertEqual(first.raw_runs, second.raw_runs)
            self.assertEqual(first.paired_differences, second.paired_differences)
            self.assertEqual(len(first.raw_runs), 12)
            self.assertEqual(len(first.paired_differences), 72)
            self.assertEqual(len(first.training_summary), 4)
            self.assertIsNotNone(
                first.strategy_results["robust"].models[3][1][
                    "trace_augmentation"
                ]
            )

            paths = save_generalization_result(
                definition,
                first,
                root / "output",
            )
            self.assertTrue(all(path.is_file() for path in paths.values()))
            with paths["manifest"].open(encoding="utf-8") as handle:
                manifest = json.load(handle)
            self.assertEqual(manifest["training_traces"], ["train.csv"])
            self.assertEqual(manifest["validation_traces"], ["validation.csv"])
            self.assertEqual(manifest["evaluation_traces"], ["evaluation.csv"])
            self.assertIsNotNone(manifest["robust_trace_augmentation"])

            invalid = GeneralizationDefinition(
                source_path=root / "invalid.json",
                experiment_version=1,
                standard_protocol=standard,
                robust_protocol=robust,
                validation_trace_paths=(train,),
            )
            with self.assertRaisesRegex(ValueError, "independentes"):
                execute_generalization_experiment(invalid)


if __name__ == "__main__":
    unittest.main()
