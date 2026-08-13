import tempfile
import unittest
from pathlib import Path

from segment_manifest import load_segment_manifest


HEADER = (
    "sequence,segment,bitrate_kbps,duration_s,size_bytes,"
    "psnr_y_db,source_file,sha256\n"
)


class SegmentManifestTest(unittest.TestCase):
    def _write(self, root: Path, rows: list[str]) -> Path:
        path = root / "segments.csv"
        path.write_text(HEADER + "".join(rows), encoding="utf-8")
        return path

    def test_loads_complete_ladder_and_optional_metadata(self):
        checksum = "A" * 64
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp),
                [
                    f"video,0,500,2.0,125000,31.2,low_0.vvc,{checksum}\n",
                    "video,0,1000,2.0,250000,34.1,high_0.vvc,\n",
                    "video,1,500,1.5,100000,,,\n",
                    "video,1,1000,1.5,210000,,,\n",
                ],
            )
            manifest = load_segment_manifest(path)
            metadata = manifest.metadata()

        self.assertEqual(manifest.sequence, "video")
        self.assertEqual(manifest.segment_count, 2)
        self.assertEqual(manifest.bitrates_kbps, (500, 1000))
        self.assertEqual(manifest.get(0, 500).size_kbits, 1000)
        self.assertEqual(manifest.get(0, 500).sha256, checksum.lower())
        self.assertIsNone(manifest.get(1, 500).psnr_y_db)
        self.assertEqual(metadata["source"], "segments.csv")
        self.assertEqual(len(metadata["manifest_sha256"]), 64)

    def test_rejects_incomplete_ladder(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp),
                [
                    "video,0,500,2.0,125000,,,\n",
                    "video,0,1000,2.0,250000,,,\n",
                    "video,1,500,2.0,125000,,,\n",
                ],
            )
            with self.assertRaisesRegex(ValueError, "incompleta"):
                load_segment_manifest(path)

    def test_rejects_different_durations_within_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp),
                [
                    "video,0,500,2.0,125000,,,\n",
                    "video,0,1000,1.5,250000,,,\n",
                ],
            )
            with self.assertRaisesRegex(ValueError, "durações diferentes"):
                load_segment_manifest(path)

    def test_rejects_missing_required_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "segments.csv"
            path.write_text(
                "sequence,segment,bitrate_kbps,duration_s\nvideo,0,500,2.0\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "size_bytes"):
                load_segment_manifest(path)

    def test_loads_canonical_representation_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canonical.csv"
            path.write_text(
                "sequence,segment,representation_id,encoder_target_kbps,"
                "bitrate_kbps,duration_s,size_bytes\n"
                "video,0,L0,1000,900,1,100000\n"
                "video,0,L1,2000,2200,1,250000\n"
                "video,1,L0,1000,900,1,125000\n"
                "video,1,L1,2000,2200,1,300000\n",
                encoding="utf-8",
            )
            manifest = load_segment_manifest(path)
            metadata = manifest.metadata()

        self.assertEqual(manifest.bitrates_kbps, (900, 2200))
        self.assertEqual(manifest.get(0, 900).representation_id, "L0")
        self.assertEqual(manifest.get(0, 900).encoder_target_kbps, 1000)
        self.assertEqual(
            metadata["representations"],
            [
                {
                    "bitrate_kbps": 900,
                    "representation_id": "L0",
                    "encoder_target_kbps": 1000,
                },
                {
                    "bitrate_kbps": 2200,
                    "representation_id": "L1",
                    "encoder_target_kbps": 2000,
                },
            ],
        )

    def test_rejects_representation_metadata_that_varies_between_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canonical.csv"
            path.write_text(
                "sequence,segment,representation_id,encoder_target_kbps,"
                "bitrate_kbps,duration_s,size_bytes\n"
                "video,0,L0,1000,900,1,100000\n"
                "video,1,,1000,900,1,125000\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "variam entre segmentos"):
                load_segment_manifest(path)


if __name__ == "__main__":
    unittest.main()
