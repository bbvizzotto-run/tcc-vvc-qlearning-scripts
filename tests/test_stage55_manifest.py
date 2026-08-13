import unittest
from pathlib import Path

from abr_baselines import BolaConfig, RobustMpcConfig
from abr_comparison import run_baseline_experiment
from experiment import ExperimentConfig
from q_learning_pipeline import (
    RewardConfig,
    TrainingConfig,
    run_q_learning_experiment,
    train_q_learning,
)
from segment_manifest import load_segment_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    ROOT / "segment_manifests/stage55/big_buck_bunny_measured.csv"
)


class Stage55ManifestIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_segment_manifest(MANIFEST_PATH)

    def test_canonical_manifest_has_the_expected_measured_ladder(self):
        self.assertEqual(self.manifest.sequence, "big_buck_bunny")
        self.assertEqual(self.manifest.segment_count, 60)
        self.assertEqual(
            self.manifest.bitrates_kbps,
            (1019, 1692, 2610, 3632),
        )
        self.assertEqual(
            [
                entry["encoder_target_kbps"]
                for entry in self.manifest.metadata()["representations"]
            ],
            [1000, 2000, 4000, 8000],
        )

    def test_manifest_runs_with_q_learning_bola_and_robust_mpc(self):
        trace = [1200.0, 1800.0, 2700.0, 4200.0, 2300.0, 3600.0]
        experiment = ExperimentConfig(
            bitrates_kbps=self.manifest.bitrates_kbps,
            segment_duration_s=1.0,
            startup_buffer_s=2.0,
            max_buffer_s=20.0,
            low_buffer_s=4.0,
            high_buffer_s=10.0,
            seed=42,
        )
        reward = RewardConfig(startup_weight=0.5, target_buffer_s=8.0)
        training = TrainingConfig(
            episodes=1,
            buffer_boundaries_s=(2.0, 4.0, 6.0, 8.0, 12.0, 16.0),
            seed=42,
            startup_guard=True,
        )
        agent, encoder, _, _ = train_q_learning(
            [("stage55-smoke", trace)],
            experiment,
            training,
            reward,
            segment_manifest=self.manifest,
        )
        q_rows, _ = run_q_learning_experiment(
            trace,
            experiment,
            agent,
            encoder,
            reward,
            segment_manifest=self.manifest,
            startup_guard=True,
        )
        bola_rows, _ = run_baseline_experiment(
            "bola-basic",
            trace,
            experiment,
            reward,
            self.manifest,
            bola_config=BolaConfig(),
        )
        mpc_rows, _ = run_baseline_experiment(
            "robust-mpc",
            trace,
            experiment,
            reward,
            self.manifest,
            robust_mpc_config=RobustMpcConfig(),
        )

        for rows in (q_rows, bola_rows, mpc_rows):
            self.assertEqual(len(rows), len(trace))
            self.assertEqual(
                {row["segment_size_source"] for row in rows},
                {"manifest"},
            )
            self.assertTrue(
                {int(row["bitrate_kbps"]) for row in rows}
                <= set(self.manifest.bitrates_kbps)
            )


if __name__ == "__main__":
    unittest.main()
