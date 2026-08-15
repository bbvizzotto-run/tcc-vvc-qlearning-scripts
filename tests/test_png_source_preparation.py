import hashlib
import json
import struct
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from png_source_preparation import (
    PNG_SIGNATURE,
    build_ffmpeg_command,
    load_png_source_config,
    parse_png_header,
    prepare_png_source,
    with_path_overrides,
)


def png_header(width=2, height=2, bit_depth=8, color_type=2):
    return (
        PNG_SIGNATURE
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + bytes([bit_depth, color_type, 0, 0, 0])
    )


class FakeDownloader:
    def __init__(self, payload=None):
        self.payload = payload or png_header()
        self.calls = []

    def __call__(self, url, destination, timeout_s, retries):
        self.calls.append((url, destination, timeout_s, retries))
        destination.write_bytes(self.payload)


class FakeFfmpegRunner:
    def __init__(self, output_bytes, returncode=0):
        self.output_bytes = output_bytes
        self.returncode = returncode
        self.commands = []

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        if self.returncode == 0:
            Path(command[-1]).write_bytes(self.output_bytes)
        return subprocess.CompletedProcess(
            command,
            self.returncode,
            "",
            "erro simulado" if self.returncode else "",
        )


class PngSourcePreparationTest(unittest.TestCase):
    def _configuration(self, root):
        path = root / "png-source.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source": {
                        "name": "tiny_pngs",
                        "base_url": "https://example.test/frames",
                        "index_url": "https://example.test/frames/",
                        "license_name": "CC BY 3.0",
                        "license_url": "https://creativecommons.org/licenses/by/3.0/",
                        "cache_dir": "cache",
                        "filename_pattern": "%05d.png",
                        "first_frame": 5,
                        "frame_count": 2,
                        "width": 2,
                        "height": 2,
                        "fps_num": 2,
                        "fps_den": 1,
                        "bit_depth": 8,
                    },
                    "clip": {
                        "output_yuv": "normalized.yuv",
                        "provenance_path": "normalized.provenance.json",
                        "width": 6,
                        "height": 6,
                        "pad_x": 2,
                        "pad_y": 2,
                        "pixel_format": "yuv420p",
                    },
                    "download": {"workers": 1, "timeout_s": 4, "retries": 2},
                    "ffmpeg_executable": "fake-ffmpeg",
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_parses_png_ihdr(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frame.png"
            path.write_bytes(png_header(1920, 800))
            header = parse_png_header(path)

        self.assertEqual((header["width"], header["height"]), (1920, 800))
        self.assertEqual(header["bit_depth"], 8)

    def test_prepares_sequence_and_writes_per_frame_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = load_png_source_config(self._configuration(root))
            downloader = FakeDownloader()
            runner = FakeFfmpegRunner(b"x" * 108)
            result = prepare_png_source(
                config,
                downloader=downloader,
                runner=runner,
                ffmpeg_info={"path": "fake-ffmpeg", "version": "ffmpeg test"},
            )
            provenance = json.loads(
                config.clip.provenance_path.read_text(encoding="utf-8")
            )

        self.assertEqual(len(downloader.calls), 2)
        self.assertEqual(result["clip"]["size_bytes"], 108)
        self.assertEqual(result["clip"]["duration_s"], 1.0)
        self.assertEqual(result["source_sequence"]["downloaded_frames"], 2)
        self.assertEqual(len(provenance["source_sequence"]["frames"]), 2)
        self.assertEqual(len(provenance["source_sequence"]["sequence_sha256"]), 64)
        self.assertFalse(provenance["source_sequence"]["integrity_pinned"])
        self.assertEqual(
            provenance["normalization"]["active_region"],
            {"x": 2, "y": 2, "width": 2, "height": 2},
        )

    def test_reuses_valid_cached_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = load_png_source_config(self._configuration(root))
            config.source.cache_dir.mkdir()
            for frame in (5, 6):
                (config.source.cache_dir / f"{frame:05d}.png").write_bytes(
                    png_header()
                )
            downloader = FakeDownloader()
            result = prepare_png_source(
                config,
                downloader=downloader,
                runner=FakeFfmpegRunner(b"x" * 108),
                ffmpeg_info={"path": "fake-ffmpeg", "version": "ffmpeg test"},
            )

        self.assertEqual(downloader.calls, [])
        self.assertEqual(result["source_sequence"]["reused_frames"], 2)

    def test_rejects_wrong_geometry_before_ffmpeg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = load_png_source_config(self._configuration(root))
            runner = FakeFfmpegRunner(b"x" * 108)
            with self.assertRaisesRegex(RuntimeError, "quadro 00005"):
                prepare_png_source(
                    config,
                    downloader=FakeDownloader(png_header(width=4)),
                    runner=runner,
                    ffmpeg_info={"path": "fake", "version": "fake"},
                )

        self.assertEqual(runner.commands, [])
        self.assertFalse((config.source.cache_dir / "00005.png").exists())

    def test_rejects_unpinned_sequence_after_hashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = load_png_source_config(self._configuration(root))
            config = replace(
                config,
                source=replace(config.source, expected_sequence_sha256="0" * 64),
            )
            runner = FakeFfmpegRunner(b"x" * 108)
            with self.assertRaisesRegex(ValueError, "agregado"):
                prepare_png_source(
                    config,
                    downloader=FakeDownloader(),
                    runner=runner,
                    ffmpeg_info={"path": "fake", "version": "fake"},
                )

        self.assertEqual(runner.commands, [])

    def test_applies_local_paths_and_builds_letterbox_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = load_png_source_config(self._configuration(root))
            overridden = with_path_overrides(
                config,
                cache_dir=root / "external-cache",
                output_yuv=root / "external.yuv",
                provenance_path=root / "external.json",
                ffmpeg_executable="D:/tools/ffmpeg.exe",
            )
            command = build_ffmpeg_command(
                overridden,
                "D:/tools/ffmpeg.exe",
                root / "temporary.yuv",
            )

        self.assertEqual(overridden.source.cache_dir.name, "external-cache")
        self.assertEqual(command[command.index("-start_number") + 1], "5")
        self.assertEqual(command[command.index("-frames:v") + 1], "2")
        self.assertIn("pad=6:6:2:2:color=black", command[command.index("-vf") + 1])


if __name__ == "__main__":
    unittest.main()
