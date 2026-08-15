import json
import tempfile
import unittest
from pathlib import Path

from abr_baselines import BolaConfig, RobustMpcConfig
from abr_comparison import run_baseline_experiment
from experiment import ExperimentConfig
from measured_ladder import canonicalize_manifest
from q_learning_pipeline import (
    RewardConfig,
    TrainingConfig,
    run_q_learning_experiment,
    train_q_learning,
)
from segment_manifest import load_segment_manifest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATHS = {
    "big_buck_bunny": (
        ROOT / "segment_manifests/stage55/big_buck_bunny_measured.csv"
    ),
    "elephants_dream": (
        ROOT / "segment_manifests/stage55/elephants_dream_measured.csv"
    ),
    "sita_sings_the_blues": (
        ROOT / "segment_manifests/stage55/sita_sings_the_blues_measured.csv"
    ),
    "tears_of_steel": (
        ROOT / "segment_manifests/stage55/tears_of_steel_measured.csv"
    ),
}


class Stage55ManifestIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifests = {
            name: load_segment_manifest(path)
            for name, path in MANIFEST_PATHS.items()
        }

    def test_canonical_manifests_have_the_expected_measured_ladders(self):
        expected = {
            "big_buck_bunny": (1019, 1692, 2610, 3632),
            "elephants_dream": (1064, 1847, 3097, 5182),
            "sita_sings_the_blues": (973, 1801, 3219, 5583),
            "tears_of_steel": (894, 1487, 2327, 3593),
        }
        for name, ladder in expected.items():
            with self.subTest(sequence=name):
                manifest = self.manifests[name]
                self.assertEqual(manifest.sequence, name)
                self.assertEqual(manifest.segment_count, 60)
                self.assertEqual(manifest.bitrates_kbps, ladder)
                self.assertEqual(
                    [
                        entry["encoder_target_kbps"]
                        for entry in manifest.metadata()["representations"]
                    ],
                    [1000, 2000, 4000, 8000],
                )

    def test_elephants_dream_records_the_lossless_edge_case(self):
        provenance_path = (
            ROOT
            / "segment_manifests/stage55/elephants_dream_measured.provenance.json"
        )
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))

        self.assertEqual(provenance["canonicalization_schema_version"], 2)
        self.assertEqual(provenance["validation"]["lossless_psnr_ties"], 6)
        self.assertFalse(
            provenance["source_execution_audit"]["pipeline"]["git_dirty"]
        )
        self.assertEqual(
            provenance["source_preparation_audit"]["source_archive"]["sha256"],
            "aef14c7ff450cd44e75760b6c0bef5ed9dc62f6af4d8c68816128ea74fb782b4",
        )
        self.assertEqual(
            provenance["source_preparation_audit"]["clip"]["sha256"],
            "8bc7a47e03d2fd1d2bd7f271a80563771579e7ce06f42cd2188a3a7a25790a80",
        )

    def test_elephants_dream_derivation_is_reproducible(self):
        directory = ROOT / "segment_manifests/stage55"
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "elephants_dream_measured.csv"
            canonicalize_manifest(
                directory / "raw/elephants_dream_full.csv",
                directory / "raw/elephants_dream_full.provenance.json",
                output,
                source_preparation_provenance=(
                    directory
                    / "raw/elephants_dream_1080p24_60s.provenance.json"
                ),
            )

            self.assertEqual(
                output.read_bytes(),
                (directory / "elephants_dream_measured.csv").read_bytes(),
            )
            self.assertEqual(
                output.with_suffix(".provenance.json").read_bytes(),
                (
                    directory
                    / "elephants_dream_measured.provenance.json"
                ).read_bytes(),
            )

    def test_sita_records_the_lossless_and_frame_rate_normalization(self):
        provenance_path = (
            ROOT
            / "segment_manifests/stage55/"
            "sita_sings_the_blues_measured.provenance.json"
        )
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))

        self.assertEqual(provenance["canonicalization_schema_version"], 2)
        self.assertEqual(provenance["validation"]["lossless_psnr_ties"], 3)
        self.assertFalse(
            provenance["source_execution_audit"]["pipeline"]["git_dirty"]
        )
        self.assertEqual(
            provenance["source_preparation_audit"]["source_archive"]["sha256"],
            "e4e8945f967ad2451d6fb663e4ef93008fea75460e6c5c1033e255a526710902",
        )
        self.assertEqual(
            provenance["source_preparation_audit"]["clip"]["sha256"],
            "c37f429197f14e63524edc7c2625b9df3be5611e89c7b0e5a9e52dc901d68a91",
        )
        self.assertEqual(
            provenance["source_preparation_audit"]["clip"]["frame_rate"],
            {
                "source_num": 24000,
                "source_den": 1001,
                "normalized_num": 24,
                "normalized_den": 1,
                "policy": "reinterpret",
                "playback_speed_factor": 1.001,
                "frame_duplication": False,
                "frame_dropping": False,
            },
        )

    def test_sita_derivation_is_reproducible(self):
        directory = ROOT / "segment_manifests/stage55"
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "sita_sings_the_blues_measured.csv"
            canonicalize_manifest(
                directory / "raw/sita_sings_the_blues_full.csv",
                directory / "raw/sita_sings_the_blues_full.provenance.json",
                output,
                source_preparation_provenance=(
                    directory
                    / "raw/sita_sings_the_blues_1080p24_60s.provenance.json"
                ),
            )

            self.assertEqual(
                output.read_bytes(),
                (directory / "sita_sings_the_blues_measured.csv").read_bytes(),
            )
            self.assertEqual(
                output.with_suffix(".provenance.json").read_bytes(),
                (
                    directory
                    / "sita_sings_the_blues_measured.provenance.json"
                ).read_bytes(),
            )

    def test_tears_records_the_pinned_png_sequence_and_active_region(self):
        provenance_path = (
            ROOT
            / "segment_manifests/stage55/tears_of_steel_measured.provenance.json"
        )
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        preparation = provenance["source_preparation_audit"]

        self.assertEqual(provenance["canonicalization_schema_version"], 2)
        self.assertEqual(provenance["validation"]["lossless_psnr_ties"], 0)
        self.assertFalse(
            provenance["source_execution_audit"]["pipeline"]["git_dirty"]
        )
        self.assertEqual(preparation["frame_records_validated"], 1440)
        self.assertTrue(preparation["quality_region_validated"])
        self.assertTrue(preparation["source_sequence"]["integrity_pinned"])
        self.assertEqual(
            preparation["source_sequence"]["sequence_sha256"],
            "1fc3a3c62782b450294563125f7d5e400d4379c4dce9a00fc237ed37fda7f48a",
        )
        self.assertEqual(
            preparation["clip"]["sha256"],
            "f6033935e2b1a8ef06d8f4d25a78b86147dcc6dfd3638c730a7ab18f59992844",
        )
        self.assertEqual(
            preparation["normalization"]["active_region"],
            {"x": 0, "y": 140, "width": 1920, "height": 800},
        )

    def test_tears_derivation_is_reproducible(self):
        directory = ROOT / "segment_manifests/stage55"
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "tears_of_steel_measured.csv"
            canonicalize_manifest(
                directory / "raw/tears_of_steel_full.csv",
                directory / "raw/tears_of_steel_full.provenance.json",
                output,
                source_preparation_provenance=(
                    directory
                    / "raw/tears_of_steel_1080p24_60s.provenance.json"
                ),
            )

            self.assertEqual(
                output.read_bytes(),
                (directory / "tears_of_steel_measured.csv").read_bytes(),
            )
            self.assertEqual(
                output.with_suffix(".provenance.json").read_bytes(),
                (
                    directory / "tears_of_steel_measured.provenance.json"
                ).read_bytes(),
            )

    def test_manifest_runs_with_q_learning_bola_and_robust_mpc(self):
        trace = [1200.0, 1800.0, 2700.0, 4200.0, 2300.0, 3600.0]
        reward = RewardConfig(startup_weight=0.5, target_buffer_s=8.0)
        training = TrainingConfig(
            episodes=1,
            buffer_boundaries_s=(2.0, 4.0, 6.0, 8.0, 12.0, 16.0),
            seed=42,
            startup_guard=True,
        )
        for name, manifest in self.manifests.items():
            with self.subTest(sequence=name):
                experiment = ExperimentConfig(
                    bitrates_kbps=manifest.bitrates_kbps,
                    segment_duration_s=1.0,
                    startup_buffer_s=2.0,
                    max_buffer_s=20.0,
                    low_buffer_s=4.0,
                    high_buffer_s=10.0,
                    seed=42,
                )
                agent, encoder, _, _ = train_q_learning(
                    [("stage55-smoke", trace)],
                    experiment,
                    training,
                    reward,
                    segment_manifest=manifest,
                )
                q_rows, _ = run_q_learning_experiment(
                    trace,
                    experiment,
                    agent,
                    encoder,
                    reward,
                    segment_manifest=manifest,
                    startup_guard=True,
                )
                bola_rows, _ = run_baseline_experiment(
                    "bola-basic",
                    trace,
                    experiment,
                    reward,
                    manifest,
                    bola_config=BolaConfig(),
                )
                mpc_rows, _ = run_baseline_experiment(
                    "robust-mpc",
                    trace,
                    experiment,
                    reward,
                    manifest,
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
                        <= set(manifest.bitrates_kbps)
                    )


if __name__ == "__main__":
    unittest.main()
