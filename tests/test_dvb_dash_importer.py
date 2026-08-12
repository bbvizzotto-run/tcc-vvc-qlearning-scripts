import csv
import json
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

from dvb_dash_importer import import_dvb_dash, parse_mpd
from segment_manifest import load_segment_manifest


MPD_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"
     type="static" mediaPresentationDuration="PT4S">
  <Period duration="PT4S">
    <AdaptationSet contentType="video" mimeType="video/mp4"
                   codecs="vvc1.1.L123" frameRate="50">
      <SegmentTemplate timescale="1000" startNumber="1"
          media="$RepresentationID$/segment-$Number%02d$.m4s"
          initialization="$RepresentationID$/init.mp4">
        <SegmentTimeline><S t="0" d="2000" r="1"/></SegmentTimeline>
      </SegmentTemplate>
      <Representation id="low" bandwidth="800000" width="1920" height="1080"/>
      <Representation id="high" bandwidth="1600000" width="1920" height="1080"/>
    </AdaptationSet>
    <AdaptationSet contentType="audio" mimeType="audio/mp4">
      <Representation id="audio" bandwidth="128000"/>
    </AdaptationSet>
  </Period>
</MPD>
"""


class DvbDashImporterTest(unittest.TestCase):
    def _package(self, root: Path) -> Path:
        mpd = root / "stream.mpd"
        mpd.write_text(MPD_TEMPLATE, encoding="utf-8")
        for representation, sizes in (("low", (101, 102)), ("high", (201, 202))):
            directory = root / representation
            directory.mkdir()
            (directory / "init.mp4").write_bytes(b"init")
            for index, size in enumerate(sizes, start=1):
                (directory / f"segment-{index:02d}.m4s").write_bytes(b"x" * size)
        return mpd

    def test_imports_segment_template_and_writes_auditable_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mpd = self._package(root)
            manifest_path = root / "out" / "dvb.csv"
            protocol_template = root / "protocol.json"
            protocol_template.write_text(
                json.dumps(
                    {
                        "protocol_version": 1,
                        "training_traces": ["train.csv"],
                        "evaluation_traces": ["eval.csv"],
                        "experiment_config": {
                            "bitrates_kbps": [500],
                            "segment_duration_s": 1.0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            protocol_output = root / "dvb_protocol.local.json"

            result = import_dvb_dash(
                mpd,
                manifest_path,
                package_name="DVB test",
                attribution="Test content owner",
                license_name="CC BY 4.0",
                license_url="https://creativecommons.org/licenses/by/4.0/",
                protocol_template_path=protocol_template,
                protocol_config_path=protocol_output,
                bandwidth_scale=10,
            )
            manifest = load_segment_manifest(manifest_path)
            provenance = json.loads(
                manifest_path.with_suffix(".provenance.json").read_text(
                    encoding="utf-8"
                )
            )
            protocol = json.loads(protocol_output.read_text(encoding="utf-8"))

        self.assertEqual(result["bitrates_kbps"], [800, 1600])
        self.assertTrue(result["adaptive_ladder"])
        self.assertEqual(manifest.segment_count, 2)
        self.assertEqual(manifest.get(0, 800).duration_s, 2.0)
        self.assertEqual(manifest.get(0, 800).size_bytes, 101)
        self.assertEqual(manifest.get(1, 1600).size_bytes, 202)
        self.assertEqual(manifest.get(0, 800).source_file, "low/segment-01.m4s")
        self.assertIsNone(manifest.get(0, 800).psnr_y_db)
        self.assertEqual(len(manifest.get(0, 800).sha256 or ""), 64)
        self.assertEqual(provenance["rights"]["license_name"], "CC BY 4.0")
        self.assertIsNone(provenance["quality"]["psnr_y_db"])
        self.assertEqual(protocol["experiment_config"]["bitrates_kbps"], [800, 1600])
        self.assertEqual(protocol["segment_manifest"], "out/dvb.csv")
        self.assertEqual(
            protocol["training_traces"],
            [{"path": "train.csv", "bandwidth_scale": 10}],
        )
        self.assertEqual(
            protocol["evaluation_traces"],
            [{"path": "eval.csv", "bandwidth_scale": 10}],
        )

    def test_filters_representations_and_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            mpd = self._package(Path(tmp))
            representations = parse_mpd(
                mpd,
                representation_ids=["high"],
                max_segments=1,
            )

        self.assertEqual(len(representations), 1)
        self.assertEqual(representations[0].representation_id, "high")
        self.assertEqual(len(representations[0].segments), 1)

    def test_supports_segment_list(self):
        mpd_text = """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">
          <Period>
            <AdaptationSet contentType="video" codecs="vvc1.1.L123">
              <Representation id="a" bandwidth="500000">
                <SegmentList timescale="10" duration="20">
                  <SegmentURL media="a-1.m4s"/><SegmentURL media="a-2.m4s"/>
                </SegmentList>
              </Representation>
              <Representation id="b" bandwidth="1000000">
                <SegmentList timescale="10" duration="20">
                  <SegmentURL media="b-1.m4s"/><SegmentURL media="b-2.m4s"/>
                </SegmentList>
              </Representation>
            </AdaptationSet>
          </Period>
        </MPD>"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mpd = root / "list.mpd"
            mpd.write_text(mpd_text, encoding="utf-8")
            for name in ("a-1.m4s", "a-2.m4s", "b-1.m4s", "b-2.m4s"):
                (root / name).write_bytes(b"payload")
            representations = parse_mpd(mpd)

        self.assertEqual([item.bitrate_kbps for item in representations], [500, 1000])
        self.assertEqual(representations[0].segments[1].duration_s, 2.0)

    def _sidx_file(
        self,
        path: Path,
        segment_payloads: tuple[bytes, ...],
        durations: tuple[int, ...] = (20, 30),
    ) -> tuple[int, int, int]:
        prefix = b"initial!"
        references = b"".join(
            struct.pack(">III", len(payload), duration, 0x90000000)
            for payload, duration in zip(segment_payloads, durations)
        )
        body = (
            b"\x00\x00\x00\x00"
            + struct.pack(">II", 1, 10)
            + struct.pack(">II", 0, 0)
            + struct.pack(">HH", 0, len(segment_payloads))
            + references
        )
        box = struct.pack(">I4s", 8 + len(body), b"sidx") + body
        path.write_bytes(prefix + box + b"".join(segment_payloads))
        index_start = len(prefix)
        index_end = index_start + len(box) - 1
        media_start = index_end + 1
        return index_start, index_end, media_start

    def test_supports_segment_base_sidx_byte_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a_payloads = (b"a" * 5, b"b" * 7)
            b_payloads = (b"c" * 11, b"d" * 13)
            index_start, index_end, media_start = self._sidx_file(
                root / "a.mp4",
                a_payloads,
            )
            self._sidx_file(root / "b.mp4", b_payloads)
            mpd = root / "base.mpd"
            mpd.write_text(
                f"""<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">
                  <Period duration="PT5S">
                    <AdaptationSet contentType="video" codecs="vvi1.1.L86.CQA">
                      <Representation id="a" bandwidth="500000">
                        <BaseURL>a.mp4</BaseURL>
                        <SegmentBase indexRange="{index_start}-{index_end}"/>
                      </Representation>
                      <Representation id="b" bandwidth="1000000">
                        <BaseURL>b.mp4</BaseURL>
                        <SegmentBase indexRange="{index_start}-{index_end}"/>
                      </Representation>
                    </AdaptationSet>
                  </Period>
                </MPD>""",
                encoding="utf-8",
            )
            output = root / "base.csv"
            import_dvb_dash(mpd, output, attribution="Test content owner")
            manifest = load_segment_manifest(output)
            provenance = json.loads(
                output.with_suffix(".provenance.json").read_text(encoding="utf-8")
            )

        first = manifest.get(0, 500)
        second = manifest.get(1, 1000)
        self.assertEqual(first.duration_s, 2.0)
        self.assertEqual(first.size_bytes, 5)
        self.assertEqual(first.source_file, f"a.mp4#bytes={media_start}-{media_start + 4}")
        self.assertEqual(first.sha256, hashlib.sha256(a_payloads[0]).hexdigest())
        self.assertEqual(second.duration_s, 3.0)
        self.assertEqual(second.size_bytes, 13)
        self.assertEqual(
            provenance["representations"][0]["addressing_mode"],
            "SegmentBase",
        )

    def test_rejects_segment_base_without_sidx(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "video.mp4").write_bytes(b"not-a-sidx-box")
            mpd = root / "invalid.mpd"
            mpd.write_text(
                """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">
                  <Period duration="PT2S"><AdaptationSet contentType="video">
                    <Representation id="a" bandwidth="500000" codecs="vvc1">
                      <BaseURL>video.mp4</BaseURL>
                      <SegmentBase indexRange="0-7"/>
                    </Representation>
                  </AdaptationSet></Period>
                </MPD>""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "não aponta.*SIDX"):
                parse_mpd(mpd)

    def test_rejects_a_missing_media_segment_before_writing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mpd = self._package(root)
            (root / "high" / "segment-02.m4s").unlink()
            output = root / "manifest.csv"
            with self.assertRaisesRegex(ValueError, "não foi encontrado"):
                import_dvb_dash(
                    mpd,
                    output,
                    attribution="Test content owner",
                )
            self.assertFalse(output.exists())

    def test_manifest_rows_do_not_include_initialization_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mpd = self._package(root)
            output = root / "manifest.csv"
            import_dvb_dash(mpd, output, attribution="Test content owner")
            with output.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 4)
        self.assertTrue(all("init" not in row["source_file"] for row in rows))


if __name__ == "__main__":
    unittest.main()
