import hashlib
import io
import json
import lzma
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from y4m_source_preparation import (
    build_ffmpeg_command,
    load_source_preparation_config,
    parse_y4m_header,
    prepare_source,
    with_path_overrides,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeStdin:
    def __init__(self, interrupt=False):
        self.data = bytearray()
        self.closed = False
        self.interrupt = interrupt

    def write(self, value):
        if self.interrupt:
            raise KeyboardInterrupt
        self.data.extend(value)
        return len(value)

    def close(self):
        self.closed = True


class FakeFfmpegProcess:
    def __init__(self, command, output_bytes, returncode=0, interrupt=False):
        self.command = command
        self.output_bytes = output_bytes
        self.configured_returncode = returncode
        self.stdin = FakeStdin(interrupt=interrupt)
        self.stderr = io.BytesIO(b"erro simulado" if returncode else b"")
        self.finished = False
        self.killed = False

    def poll(self):
        return self.configured_returncode if self.finished else None

    def wait(self):
        if not self.finished:
            if self.configured_returncode == 0:
                Path(self.command[-1]).write_bytes(self.output_bytes)
            self.finished = True
        return self.configured_returncode

    def kill(self):
        self.killed = True
        self.configured_returncode = -9
        self.finished = True


class FakePopenFactory:
    def __init__(self, output_bytes, returncode=0, interrupt=False):
        self.output_bytes = output_bytes
        self.returncode = returncode
        self.interrupt = interrupt
        self.processes = []

    def __call__(self, command, **kwargs):
        self.asserted_kwargs = kwargs
        process = FakeFfmpegProcess(
            command,
            self.output_bytes,
            self.returncode,
            self.interrupt,
        )
        self.processes.append(process)
        return process


class Y4MSourcePreparationTest(unittest.TestCase):
    def _archive(self, root: Path) -> Path:
        path = root / "source.y4m.xz"
        content = (
            b"YUV4MPEG2 W2 H2 F2:1 Ip A1:1 C420jpeg\n"
            b"FRAME\nabcdef"
            b"FRAME\nghijkl"
            b"FRAME\nmnopqr"
        )
        with lzma.open(path, "wb") as handle:
            handle.write(content)
        return path

    def _configuration(self, root: Path, archive: Path) -> Path:
        path = root / "source.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source": {
                        "name": "tiny",
                        "url": "https://example.test/source.y4m.xz",
                        "license_name": "CC BY 2.5",
                        "license_url": "https://creativecommons.org/licenses/by/2.5/",
                        "input_xz": archive.name,
                        "expected_sha256": hashlib.sha256(
                            archive.read_bytes()
                        ).hexdigest(),
                    },
                    "clip": {
                        "output_yuv": "normalized.yuv",
                        "provenance_path": "normalized.provenance.json",
                        "width": 2,
                        "height": 2,
                        "fps_num": 2,
                        "fps_den": 1,
                        "start_frame": 1,
                        "frame_count": 2,
                        "pixel_format": "yuv420p",
                    },
                    "ffmpeg_executable": "fake-ffmpeg",
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_parses_supported_progressive_y4m_header(self):
        header = parse_y4m_header(
            b"YUV4MPEG2 W1920 H1080 F24:1 Ip A1:1 C420mpeg2\n"
        )
        self.assertEqual((header.width, header.height), (1920, 1080))
        self.assertEqual((header.fps_num, header.fps_den), (24, 1))
        self.assertEqual(header.chroma, "420mpeg2")

    def test_rejects_ten_bit_or_interlaced_input(self):
        with self.assertRaisesRegex(ValueError, "4:2:0 de 8 bits"):
            parse_y4m_header(
                b"YUV4MPEG2 W1920 H1080 F24:1 Ip A1:1 C420p10\n"
            )
        with self.assertRaisesRegex(ValueError, "progressiva"):
            parse_y4m_header(
                b"YUV4MPEG2 W1920 H1080 F24:1 It A1:1 C420jpeg\n"
            )

    def test_prepares_clip_and_writes_auditable_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._archive(root)
            config = load_source_preparation_config(
                self._configuration(root, archive)
            )
            factory = FakePopenFactory(b"x" * 12)
            result = prepare_source(
                config,
                popen_factory=factory,
                ffmpeg_info={"path": "fake-ffmpeg", "version": "ffmpeg test"},
            )
            provenance = json.loads(
                config.clip.provenance_path.read_text(encoding="utf-8")
            )

            self.assertEqual(config.clip.output_yuv.read_bytes(), b"x" * 12)
            self.assertEqual(result["clip"]["frame_count"], 2)
            self.assertEqual(result["clip"]["duration_s"], 1.0)
            self.assertEqual(
                provenance["source_archive"]["sha256"],
                config.source.expected_sha256,
            )
            self.assertEqual(
                provenance["source_archive"]["y4m_header"]["chroma"],
                "420jpeg",
            )
            self.assertIn(b"YUV4MPEG2", factory.processes[0].stdin.data)
            self.assertTrue(factory.processes[0].stdin.closed)

    def test_rejects_wrong_archive_hash_before_starting_ffmpeg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._archive(root)
            config = load_source_preparation_config(
                self._configuration(root, archive)
            )
            bad_config = replace(
                config,
                source=replace(config.source, expected_sha256="0" * 64),
            )
            factory = FakePopenFactory(b"x" * 12)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                prepare_source(
                    bad_config,
                    popen_factory=factory,
                    ffmpeg_info={"path": "fake", "version": "fake"},
                )
            self.assertEqual(factory.processes, [])

    def test_applies_local_paths_without_changing_the_frozen_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._archive(root)
            config = load_source_preparation_config(
                self._configuration(root, archive)
            )
            overridden = with_path_overrides(
                config,
                input_xz=root / "download.xz",
                output_yuv=root / "external.yuv",
                provenance_path=root / "external.provenance.json",
                ffmpeg_executable="D:/tools/ffmpeg.exe",
            )

        self.assertEqual(overridden.source.name, config.source.name)
        self.assertEqual(overridden.source.input_xz.name, "download.xz")
        self.assertEqual(overridden.clip.output_yuv.name, "external.yuv")
        self.assertEqual(
            overridden.clip.provenance_path.name,
            "external.provenance.json",
        )
        self.assertEqual(overridden.ffmpeg_executable, "D:/tools/ffmpeg.exe")

    def test_rejects_header_that_differs_from_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._archive(root)
            config_path = self._configuration(root, archive)
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            raw["clip"]["fps_num"] = 24
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            config = load_source_preparation_config(config_path)
            factory = FakePopenFactory(b"x" * 12)
            with self.assertRaisesRegex(ValueError, "difere da configuração"):
                prepare_source(
                    config,
                    popen_factory=factory,
                    ffmpeg_info={"path": "fake", "version": "fake"},
                )
            self.assertFalse(config.clip.output_yuv.exists())

    def test_refuses_existing_outputs_and_reports_ffmpeg_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._archive(root)
            config = load_source_preparation_config(
                self._configuration(root, archive)
            )
            config.clip.output_yuv.write_bytes(b"existing")
            with self.assertRaisesRegex(FileExistsError, "--overwrite"):
                prepare_source(
                    config,
                    popen_factory=FakePopenFactory(b"x" * 12),
                    ffmpeg_info={"path": "fake", "version": "fake"},
                )
            config.clip.output_yuv.unlink()
            with self.assertRaisesRegex(RuntimeError, "erro simulado"):
                prepare_source(
                    config,
                    popen_factory=FakePopenFactory(b"", returncode=1),
                    ffmpeg_info={"path": "fake", "version": "fake"},
                )

    def test_interrupt_terminates_ffmpeg_and_removes_temporary_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._archive(root)
            config = load_source_preparation_config(
                self._configuration(root, archive)
            )
            factory = FakePopenFactory(b"", interrupt=True)
            with self.assertRaises(KeyboardInterrupt):
                prepare_source(
                    config,
                    popen_factory=factory,
                    ffmpeg_info={"path": "fake", "version": "fake"},
                )

            self.assertTrue(factory.processes[0].killed)
            self.assertFalse(config.clip.output_yuv.exists())
            self.assertFalse(
                config.clip.output_yuv.with_suffix(".yuv.tmp").exists()
            )

    def test_builds_the_frozen_trim_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self._archive(root)
            config = load_source_preparation_config(
                self._configuration(root, archive)
            )
            command = build_ffmpeg_command(
                config,
                "ffmpeg",
                root / "output.tmp",
            )
        self.assertIn("trim=start_frame=1:end_frame=3,setpts=PTS-STARTPTS", command)
        self.assertEqual(command[command.index("-frames:v") + 1], "2")
        self.assertEqual(command[command.index("-fps_mode") + 1], "passthrough")

    def test_sita_configuration_freezes_the_multi_content_protocol(self):
        config = load_source_preparation_config(
            ROOT / "y4m_source_config.sita_sings_the_blues.json"
        )

        self.assertEqual(config.source.name, "sita_sings_the_blues")
        self.assertEqual(
            config.source.expected_sha256,
            "e4e8945f967ad2451d6fb663e4ef93008fea75460e6c5c1033e255a526710902",
        )
        self.assertEqual(
            config.source.license_name,
            "CC0 1.0 Universal (visual content)",
        )
        self.assertEqual((config.clip.width, config.clip.height), (1920, 1080))
        self.assertEqual((config.clip.fps_num, config.clip.fps_den), (24, 1))
        self.assertEqual(config.clip.start_frame, 2880)
        self.assertEqual(config.clip.frame_count, 1440)
        self.assertEqual(config.clip.duration_s, 60.0)
        self.assertEqual(config.clip.expected_output_size_bytes, 4478976000)


if __name__ == "__main__":
    unittest.main()
