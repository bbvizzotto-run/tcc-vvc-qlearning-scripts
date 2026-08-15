import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from measured_ladder import canonicalize_manifest
from segment_manifest import load_segment_manifest


class MeasuredLadderTest(unittest.TestCase):
    def _raw_manifest(
        self,
        root: Path,
        *,
        invert_psnr: bool = False,
        lossless_second_segment: bool = False,
    ) -> Path:
        path = root / "raw.csv"
        low_second_psnr = "100" if lossless_second_segment else "31"
        high_second_psnr = (
            "100"
            if lossless_second_segment
            else ("30" if invert_psnr else "34")
        )
        path.write_text(
            "sequence,segment,bitrate_kbps,duration_s,size_bytes,"
            "psnr_y_db,source_file,sha256\n"
            f"video,0,1000,1,100000,30,low0.266,{'a' * 64}\n"
            f"video,0,2000,1,250000,33,high0.266,{'b' * 64}\n"
            f"video,1,1000,1,125000,{low_second_psnr},low1.266,"
            f"{'c' * 64}\n"
            f"video,1,2000,1,300000,{high_second_psnr},high1.266,"
            f"{'d' * 64}\n",
            encoding="utf-8",
        )
        return path

    def _source_provenance(self, root: Path, *, targets=None) -> Path:
        configured_targets = targets or [1000, 2000]
        commands = []
        for segment in range(2):
            for bitrate in (1000, 2000):
                commands.append(
                    {
                        "segment": segment,
                        "bitrate_kbps": bitrate,
                        "encoder": [
                            "vvencapp",
                            "--additional",
                            "POC0IDR=1",
                        ],
                        "encoder_reused": False,
                        "decoder": ["vvdecapp"],
                    }
                )
        path = root / "raw.provenance.json"
        path.write_text(
            json.dumps(
                {
                    "pipeline_schema_version": 1,
                    "generated_at_utc": "2026-01-01T00:00:00+00:00",
                    "configuration_sha256": "e" * 64,
                    "configuration": {
                        "source": {"segment_count": 2},
                        "bitrates_kbps": configured_targets,
                        "encoder": {"refresh_type": "idr_no_radl"},
                        "decoder": {
                            "quality_region": {
                                "x": 2,
                                "y": 2,
                                "width": 2,
                                "height": 2,
                            }
                        },
                    },
                    "pipeline": {"git_commit": "abc", "git_dirty": False},
                    "source": {
                        "sha256": "f" * 64,
                        "size_bytes": 12,
                        "available_frames": 2,
                    },
                    "tools": {"encoder": {"version": "VVenC 1.14.0"}},
                    "runtime": {"platform": "test"},
                    "commands": commands,
                    "manifest": {
                        "source": "raw.csv",
                        "manifest_sha256": hashlib.sha256(
                            (root / "raw.csv").read_bytes()
                        ).hexdigest(),
                        "sequence": "video",
                        "segment_count": 2,
                        "bitrates_kbps": [1000, 2000],
                        "size_unit": "bytes",
                    },
                }
            ),
            encoding="utf-8",
        )
        return path

    def _png_source_preparation_provenance(self, root: Path) -> Path:
        path = root / "png-source-preparation.provenance.json"
        frame_records = [
            {
                "frame_number": 5,
                "filename": "00005.png",
                "size_bytes": 10,
                "sha256": "a" * 64,
                "png": {
                    "width": 2,
                    "height": 2,
                    "bit_depth": 8,
                    "color_type": 2,
                    "compression_method": 0,
                    "filter_method": 0,
                    "interlace_method": 0,
                },
            },
            {
                "frame_number": 6,
                "filename": "00006.png",
                "size_bytes": 20,
                "sha256": "b" * 64,
                "png": {
                    "width": 2,
                    "height": 2,
                    "bit_depth": 8,
                    "color_type": 2,
                    "compression_method": 0,
                    "filter_method": 0,
                    "interlace_method": 0,
                },
            },
        ]
        aggregate = hashlib.sha256()
        for record in frame_records:
            aggregate.update(
                (
                    f"{record['filename']}\t{record['size_bytes']}\t"
                    f"{record['sha256']}\n"
                ).encode("ascii")
            )
        sequence_sha256 = aggregate.hexdigest()
        source = {
            "name": "video",
            "base_url": "https://example.test/frames/",
            "index_url": "https://example.test/frames/",
            "license_name": "CC BY 3.0",
            "license_url": "https://creativecommons.org/licenses/by/3.0/",
            "filename_pattern": "%05d.png",
            "first_frame": 5,
            "frame_count": 2,
            "width": 2,
            "height": 2,
            "fps_num": 2,
            "fps_den": 1,
            "bit_depth": 8,
            "expected_sequence_sha256": sequence_sha256,
        }
        path.write_text(
            json.dumps(
                {
                    "preparation_schema_version": 1,
                    "generated_at_utc": "2026-01-01T00:00:00+00:00",
                    "configuration_sha256": "3" * 64,
                    "configuration": {
                        "source": source,
                        "clip": {
                            "width": 6,
                            "height": 6,
                            "pad_x": 2,
                            "pad_y": 2,
                            "pixel_format": "yuv420p",
                        },
                    },
                    "source_sequence": {
                        **{
                            key: value
                            for key, value in source.items()
                            if key
                            not in (
                                "filename_pattern",
                                "bit_depth",
                                "expected_sequence_sha256",
                            )
                        },
                        "last_frame": 6,
                        "duration_s": 1.0,
                        "total_size_bytes": 30,
                        "sequence_sha256": sequence_sha256,
                        "expected_sequence_sha256": sequence_sha256,
                        "integrity_pinned": True,
                        "downloaded_frames": 2,
                        "reused_frames": 0,
                        "frames": frame_records,
                    },
                    "normalization": {
                        "policy": "symmetric_letterbox",
                        "pad_x": 2,
                        "pad_y": 2,
                        "color": "black",
                        "active_region": {
                            "x": 2,
                            "y": 2,
                            "width": 2,
                            "height": 2,
                        },
                    },
                    "clip": {
                        "width": 6,
                        "height": 6,
                        "pixel_format": "yuv420p",
                        "frame_count": 2,
                        "duration_s": 1.0,
                        "size_bytes": 12,
                        "sha256": "f" * 64,
                    },
                    "pipeline": {"git_commit": "abc", "git_dirty": False},
                    "runtime": {"platform": "test"},
                }
            ),
            encoding="utf-8",
        )
        return path

    def _source_preparation_provenance(
        self,
        root: Path,
        *,
        clip_sha256: str | None = None,
    ) -> Path:
        path = root / "source-preparation.provenance.json"
        archive_sha256 = "1" * 64
        path.write_text(
            json.dumps(
                {
                    "source_preparation_schema_version": 1,
                    "generated_at_utc": "2026-01-01T00:00:00+00:00",
                    "configuration_sha256": "2" * 64,
                    "configuration": {
                        "source": {
                            "url": "https://example.test/source.y4m.xz",
                            "expected_sha256": archive_sha256,
                        },
                        "clip": {
                            "start_frame": 0,
                            "frame_count": 2,
                            "pixel_format": "yuv420p",
                        },
                    },
                    "source_archive": {
                        "url": "https://example.test/source.y4m.xz",
                        "sha256": archive_sha256,
                    },
                    "clip": {
                        "start_frame": 0,
                        "frame_count": 2,
                        "pixel_format": "yuv420p",
                        "size_bytes": 12,
                        "sha256": clip_sha256 or "f" * 64,
                    },
                    "ffmpeg": {"version": "ffmpeg test"},
                    "pipeline": {"git_commit": "abc", "git_dirty": False},
                    "runtime": {"platform": "test"},
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_canonicalizes_measured_ladder_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = self._raw_manifest(root)
            source_provenance = self._source_provenance(root)
            output = root / "canonical.csv"
            result = canonicalize_manifest(raw, source_provenance, output)
            first_csv = output.read_bytes()
            first_provenance = output.with_suffix(".provenance.json").read_bytes()

            canonicalize_manifest(
                raw,
                source_provenance,
                output,
                overwrite=True,
            )
            manifest = load_segment_manifest(output)
            with output.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(output.read_bytes(), first_csv)
            self.assertEqual(
                output.with_suffix(".provenance.json").read_bytes(),
                first_provenance,
            )

        self.assertEqual(manifest.bitrates_kbps, (900, 2200))
        self.assertEqual(rows[0]["representation_id"], "L0")
        self.assertEqual(rows[0]["encoder_target_kbps"], "1000")
        self.assertEqual(rows[0]["bitrate_kbps"], "900")
        self.assertEqual(
            result["output"]["operational_bitrates_kbps"],
            [900, 2200],
        )
        self.assertEqual(
            result["representations"][0]["measured_bitrate_kbps"],
            "900",
        )
        self.assertEqual(result["source_execution_audit"]["commands_validated"], 4)
        self.assertEqual(result["canonicalization_schema_version"], 2)
        self.assertEqual(result["validation"]["lossless_psnr_ties"], 0)

    def test_refuses_to_replace_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = self._raw_manifest(root)
            source_provenance = self._source_provenance(root)
            output = root / "canonical.csv"
            output.write_text("existing", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "--overwrite"):
                canonicalize_manifest(raw, source_provenance, output)

    def test_rejects_output_provenance_that_would_replace_the_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = self._raw_manifest(root)
            source_provenance = self._source_provenance(root)
            output = root / "canonical.csv"
            with self.assertRaisesRegex(ValueError, "arquivo distinto"):
                canonicalize_manifest(
                    raw,
                    source_provenance,
                    output,
                    output_provenance=output,
                )

    def test_rejects_non_monotonic_psnr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "psnr_y_db"):
                canonicalize_manifest(
                    self._raw_manifest(root, invert_psnr=True),
                    self._source_provenance(root),
                    root / "canonical.csv",
                )

    def test_accepts_equal_psnr_only_at_the_lossless_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = canonicalize_manifest(
                self._raw_manifest(root, lossless_second_segment=True),
                self._source_provenance(root),
                root / "canonical.csv",
            )

        self.assertEqual(result["validation"]["lossless_psnr_cap_db"], "100")
        self.assertEqual(result["validation"]["lossless_psnr_ties"], 1)

    def test_audits_the_source_preparation_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = canonicalize_manifest(
                self._raw_manifest(root),
                self._source_provenance(root),
                root / "canonical.csv",
                source_preparation_provenance=(
                    self._source_preparation_provenance(root)
                ),
            )

        self.assertEqual(
            result["source_preparation_audit"]["clip"]["sha256"],
            "f" * 64,
        )

    def test_rejects_a_different_prepared_source_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "hash do YUV preparado"):
                canonicalize_manifest(
                    self._raw_manifest(root),
                    self._source_provenance(root),
                    root / "canonical.csv",
                    source_preparation_provenance=(
                        self._source_preparation_provenance(
                            root,
                            clip_sha256="0" * 64,
                        )
                    ),
                )

    def test_audits_the_png_source_preparation_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = canonicalize_manifest(
                self._raw_manifest(root),
                self._source_provenance(root),
                root / "canonical.csv",
                source_preparation_provenance=(
                    self._png_source_preparation_provenance(root)
                ),
            )

        audit = result["source_preparation_audit"]
        self.assertEqual(audit["frame_records_validated"], 2)
        self.assertTrue(audit["quality_region_validated"])

    def test_rejects_png_quality_region_different_from_active_region(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = self._raw_manifest(root)
            source_provenance = self._source_provenance(root)
            provenance = json.loads(
                source_provenance.read_text(encoding="utf-8")
            )
            provenance["configuration"]["decoder"]["quality_region"]["y"] = 0
            source_provenance.write_text(
                json.dumps(provenance),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "região de qualidade VVC"):
                canonicalize_manifest(
                    raw,
                    source_provenance,
                    root / "canonical.csv",
                    source_preparation_provenance=(
                        self._png_source_preparation_provenance(root)
                    ),
                )

    def test_rejects_equal_psnr_below_the_lossless_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = self._raw_manifest(root)
            raw.write_text(
                raw.read_text(encoding="utf-8").replace(
                    ",34,high1.266,",
                    ",31,high1.266,",
                ),
                encoding="utf-8",
            )
            source_provenance = self._source_provenance(root)
            provenance = json.loads(source_provenance.read_text(encoding="utf-8"))
            provenance["manifest"]["manifest_sha256"] = hashlib.sha256(
                raw.read_bytes()
            ).hexdigest()
            source_provenance.write_text(json.dumps(provenance), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "psnr_y_db"):
                canonicalize_manifest(
                    raw,
                    source_provenance,
                    root / "canonical.csv",
                )

    def test_rejects_provenance_with_a_different_ladder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "escada da proveniência"):
                canonicalize_manifest(
                    self._raw_manifest(root),
                    self._source_provenance(root, targets=[1000, 4000]),
                    root / "canonical.csv",
                )

    def test_rejects_provenance_with_a_different_manifest_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = self._raw_manifest(root)
            source_provenance = self._source_provenance(root)
            provenance = json.loads(source_provenance.read_text(encoding="utf-8"))
            provenance["manifest"]["manifest_sha256"] = "0" * 64
            source_provenance.write_text(
                json.dumps(provenance),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "hash do manifesto"):
                canonicalize_manifest(
                    raw,
                    source_provenance,
                    root / "canonical.csv",
                )


if __name__ == "__main__":
    unittest.main()
