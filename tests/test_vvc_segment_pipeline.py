import json
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

from segment_manifest import load_segment_manifest
from vvc_segment_pipeline import (
    build_dry_run_plan,
    build_encoder_command,
    build_jobs,
    execute_pipeline,
    load_pipeline_config,
    validate_source,
)


class FakeCodecRunner:
    def __init__(self, source_path: Path, frame_size: int, frames_per_segment: int):
        self.source_path = source_path
        self.frame_size = frame_size
        self.frames_per_segment = frames_per_segment
        self.commands = []

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        if command[0] == "fake-vvencapp":
            output = Path(command[command.index("--output") + 1])
            bitrate = int(command[command.index("--bitrate") + 1])
            frame_skip = int(command[command.index("--frameskip") + 1])
            output.write_bytes(bytes([frame_skip % 256]) * (bitrate // 1000 + 1))
        elif command[0] == "fake-vvdecapp":
            bitstream = Path(command[command.index("--bitstream") + 1])
            output = Path(command[command.index("--output") + 1])
            segment = int(bitstream.stem.split("_")[-1])
            with self.source_path.open("rb") as source:
                source.seek(segment * self.frames_per_segment * self.frame_size)
                output.write_bytes(
                    source.read(self.frames_per_segment * self.frame_size)
                )
        else:
            return subprocess.CompletedProcess(command, 1, "", "ferramenta inesperada")
        return subprocess.CompletedProcess(command, 0, "ok", "")


class VvcSegmentPipelineTest(unittest.TestCase):
    def _configuration(self, root: Path, segment_count: int = 2) -> Path:
        path = root / "pipeline.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source": {
                        "name": "Tiny Sequence",
                        "input_yuv": "tiny.yuv",
                        "width": 2,
                        "height": 2,
                        "fps_num": 2,
                        "fps_den": 1,
                        "bit_depth": 8,
                        "start_frame": 0,
                        "segment_count": segment_count,
                        "segment_duration_s": 1.0,
                    },
                    "bitrates_kbps": [500, 1000],
                    "output_dir": "artifacts",
                    "manifest_path": "segments/measured.csv",
                    "encoder": {
                        "executable": "fake-vvencapp",
                        "preset": "medium",
                        "passes": 2,
                        "qpa": True,
                        "internal_bit_depth": 8,
                        "refresh_type": "idr_no_radl",
                        "threads": 2,
                        "mt_profile": 0,
                        "minimum_version": "1.13.0",
                    },
                    "decoder": {
                        "executable": "fake-vvdecapp",
                        "compute_psnr_y": True,
                        "keep_reconstructions": False,
                    },
                    "hash_source": True,
                }
            ),
            encoding="utf-8",
        )
        return path

    def _write_source(self, root: Path, frames: int = 4) -> Path:
        path = root / "tiny.yuv"
        frame_size = 6
        path.write_bytes(
            b"".join(bytes([frame]) * frame_size for frame in range(frames))
        )
        return path

    def test_builds_matrix_and_uses_bitrate_in_bits_per_second(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = load_pipeline_config(self._configuration(root))
            jobs = build_jobs(config)
            command = build_encoder_command(config, jobs[0])

        self.assertEqual(len(jobs), 4)
        self.assertEqual(command[command.index("--bitrate") + 1], "500000")
        self.assertEqual(command[command.index("--frames") + 1], "2")
        self.assertEqual(command[command.index("--frameskip") + 1], "0")
        self.assertEqual(command[command.index("--mtprofile") + 1], "0")
        self.assertIn("idr_no_radl", command)

    def test_dry_run_does_not_require_source_or_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_pipeline_config(self._configuration(Path(tmp)))
            plan = build_dry_run_plan(config)

        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["job_count"], 4)
        self.assertEqual(len(plan["jobs"]), 4)

    def test_source_validation_never_loops_short_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_source(root, frames=2)
            config = load_pipeline_config(self._configuration(root))
            with self.assertRaisesRegex(ValueError, "não repete conteúdo"):
                validate_source(config)

    def test_executes_codecs_and_generates_valid_manifest_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._write_source(root)
            config = load_pipeline_config(self._configuration(root))
            runner = FakeCodecRunner(source, frame_size=6, frames_per_segment=2)
            tools = {
                "encoder": {
                    "path": "fake-vvencapp",
                    "version": "VVenC 1.14.0",
                },
                "decoder": {
                    "path": "fake-vvdecapp",
                    "version": "VVdeC 3.0.0",
                },
            }

            result = execute_pipeline(config, runner=runner, tools=tools)
            manifest = load_segment_manifest(config.manifest_path)
            provenance_path = config.manifest_path.with_suffix(
                ".provenance.json"
            )
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))

            self.assertEqual(result["artifacts"], 4)
            self.assertEqual(manifest.segment_count, 2)
            self.assertEqual(manifest.bitrates_kbps, (500, 1000))
            self.assertEqual(manifest.get(0, 500).psnr_y_db, 100.0)
            self.assertEqual(manifest.get(0, 500).size_bytes, 501)
            self.assertFalse(
                any(config.output_dir.rglob("*.recon.yuv"))
            )
            self.assertEqual(provenance["source"]["available_frames"], 4)
            self.assertEqual(provenance["tools"]["encoder"]["version"], "VVenC 1.14.0")
            self.assertEqual(len(provenance["pipeline"]["module_sha256"]), 64)
            self.assertEqual(len(provenance["commands"]), 4)

    def test_refuses_to_replace_an_existing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_source(root)
            config = load_pipeline_config(self._configuration(root))
            config.manifest_path.parent.mkdir(parents=True)
            config.manifest_path.write_text("existente", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "--overwrite"):
                execute_pipeline(config, tools={})

    def test_resume_reuses_only_a_bitstream_with_matching_command_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._write_source(root)
            config = load_pipeline_config(self._configuration(root))
            runner = FakeCodecRunner(source, frame_size=6, frames_per_segment=2)
            tools = {
                "encoder": {
                    "path": "fake-vvencapp",
                    "version": "VVenC 1.14.0",
                },
                "decoder": {
                    "path": "fake-vvdecapp",
                    "version": "VVdeC 3.0.0",
                },
            }
            first_job = build_jobs(config)[0]
            first_job.bitstream_path.parent.mkdir(parents=True)
            first_job.bitstream_path.write_bytes(b"partial")
            encoder_command = build_encoder_command(config, first_job)
            first_job.log_path.write_text(
                "$ " + shlex.join(encoder_command) + "\n",
                encoding="utf-8",
            )

            execute_pipeline(
                config,
                resume=True,
                runner=runner,
                tools=tools,
            )
            provenance = json.loads(
                config.manifest_path.with_suffix(".provenance.json").read_text(
                    encoding="utf-8"
                )
            )

        encoder_calls = [
            command for command in runner.commands if command[0] == "fake-vvencapp"
        ]
        self.assertEqual(len(encoder_calls), 3)
        self.assertTrue(provenance["commands"][0]["encoder_reused"])


if __name__ == "__main__":
    unittest.main()
