import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiment import ExperimentConfig, load_bandwidth_trace
from experimental_protocol import ProtocolDefinition
from q_learning_pipeline import RewardConfig, TrainingConfig
from reward_tuning import (
    RewardCandidate,
    RewardTuningDefinition,
    _select_candidate,
    execute_reward_tuning,
    save_reward_tuning_result,
)


class RewardTuningTest(unittest.TestCase):
    def test_selection_prefers_payload_among_noninferior_candidates(self):
        candidates = (
            RewardCandidate("a", RewardConfig(rebuffering_weight=10)),
            RewardCandidate("b", RewardConfig(rebuffering_weight=20)),
        )
        paired = [
            {
                "candidate_id": "a",
                "scope": "overall_per_seed",
                "metric": "rebuffering_rate_percent",
                "mean": -1.0,
                "ci95_low": -2.0,
                "ci95_high": -0.1,
            },
            {
                "candidate_id": "a",
                "scope": "overall_per_seed",
                "metric": "average_payload_bitrate_kbps",
                "mean": 100.0,
                "ci95_low": 50.0,
                "ci95_high": 150.0,
            },
            {
                "candidate_id": "b",
                "scope": "overall_per_seed",
                "metric": "rebuffering_rate_percent",
                "mean": -0.5,
                "ci95_low": -1.5,
                "ci95_high": -0.2,
            },
            {
                "candidate_id": "b",
                "scope": "overall_per_seed",
                "metric": "average_payload_bitrate_kbps",
                "mean": 200.0,
                "ci95_low": 100.0,
                "ci95_high": 300.0,
            },
        ]

        rows, selected, mode = _select_candidate(candidates, paired, 0.0)

        self.assertEqual(selected, "b")
        self.assertEqual(mode, "eligible_max_payload")
        self.assertTrue(rows[0]["selected"])

    def test_execution_never_opens_evaluation_trace_and_persists_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            train = root / "train.csv"
            validation = root / "validation.csv"
            evaluation = root / "evaluation.csv"
            manifest = root / "segments.csv"
            protocol_path = root / "protocol.json"
            for path, values in (
                (train, (1600, 1300, 700, 1400)),
                (validation, (1500, 500, 1300, 600)),
                (evaluation, (1200, 400, 1000, 300)),
            ):
                path.write_text(
                    "segment,bandwidth_kbps\n"
                    + "".join(
                        f"{index},{value}\n"
                        for index, value in enumerate(values)
                    ),
                    encoding="utf-8",
                )
            manifest.write_text(
                "sequence,segment,bitrate_kbps,duration_s,size_bytes\n"
                + "".join(
                    f"video,{segment},{bitrate},2,{bitrate * 250}\n"
                    for segment in range(4)
                    for bitrate in (500, 1000)
                ),
                encoding="utf-8",
            )
            protocol_path.write_text(
                json.dumps(
                    {
                        "protocol_version": 1,
                        "seeds": [3, 7],
                        "training_traces": ["train.csv"],
                        "evaluation_traces": ["evaluation.csv"],
                        "experiment_config": {
                            "bitrates_kbps": [500, 1000],
                            "segment_duration_s": 2,
                            "startup_buffer_s": 2,
                            "max_buffer_s": 10,
                        },
                        "training_config": {
                            "episodes": 12,
                            "epsilon_decay": 0.9,
                            "epsilon_min": 0.05,
                            "buffer_boundaries_s": [2, 4, 8],
                        },
                        "reward_config": {"target_buffer_s": 4},
                        "segment_manifest": "segments.csv",
                    }
                ),
                encoding="utf-8",
            )
            protocol = ProtocolDefinition(
                source_path=protocol_path,
                protocol_version=1,
                confidence_level=0.95,
                seeds=(3, 7),
                training_trace_paths=(train,),
                evaluation_trace_paths=(evaluation,),
                experiment_config=ExperimentConfig(
                    bitrates_kbps=(500, 1000),
                    segment_duration_s=2,
                    startup_buffer_s=2,
                    max_buffer_s=10,
                    seed=3,
                ),
                training_config=TrainingConfig(
                    episodes=12,
                    epsilon_decay=0.9,
                    epsilon_min=0.05,
                    buffer_boundaries_s=(2, 4, 8),
                    seed=3,
                ),
                reward_config=RewardConfig(target_buffer_s=4),
                segment_manifest_path=manifest,
            )
            definition = RewardTuningDefinition(
                source_path=root / "tuning.json",
                tuning_version=1,
                base_protocol=protocol,
                validation_trace_paths=(validation,),
                validation_trace_scales=(1.0,),
                candidates=(
                    RewardCandidate(
                        "wr10",
                        RewardConfig(rebuffering_weight=10, target_buffer_s=4),
                    ),
                    RewardCandidate(
                        "wr20",
                        RewardConfig(rebuffering_weight=20, target_buffer_s=4),
                    ),
                ),
            )
            opened: list[Path] = []

            def guarded_loader(path):
                resolved = Path(path).resolve()
                opened.append(resolved)
                if resolved == evaluation.resolve():
                    raise AssertionError("trace de avaliação foi aberto")
                return load_bandwidth_trace(resolved)

            with patch("reward_tuning.load_bandwidth_trace", guarded_loader):
                result = execute_reward_tuning(definition)

            self.assertNotIn(evaluation.resolve(), opened)
            self.assertEqual(len(result.raw_runs), 6)
            self.assertIn(result.selected_candidate_id, {"wr10", "wr20"})
            paths = save_reward_tuning_result(
                definition,
                result,
                root / "output",
                root / "selected_protocol.json",
            )
            self.assertTrue(all(path.is_file() for path in paths.values()))
            with paths["manifest"].open(encoding="utf-8") as handle:
                saved_manifest = json.load(handle)
            self.assertEqual(
                saved_manifest["evaluation_traces_frozen"],
                ["evaluation.csv"],
            )
            with paths["selected_protocol"].open(encoding="utf-8") as handle:
                selected_protocol = json.load(handle)
            self.assertEqual(
                selected_protocol["selection_provenance"]["evaluation_status"],
                "frozen_not_executed_during_selection",
            )


if __name__ == "__main__":
    unittest.main()
