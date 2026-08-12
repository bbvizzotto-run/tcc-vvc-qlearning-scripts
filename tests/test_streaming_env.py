import unittest

from segment_manifest import SegmentManifest, SegmentMetadata
from streaming_env import StreamingConfig, StreamingEnvironment


class StreamingEnvironmentTest(unittest.TestCase):
    def test_startup_delay_is_not_rebuffering(self):
        env = StreamingEnvironment(
            [1000, 1000],
            StreamingConfig(segment_duration_s=2, startup_buffer_s=4, max_buffer_s=10),
        )

        first = env.step(1000)
        second = env.step(1000)

        self.assertEqual(first.startup_delay_s, 2)
        self.assertEqual(second.startup_delay_s, 2)
        self.assertEqual(env.total_rebuffering_s, 0)
        self.assertTrue(second.playback_started)
        self.assertEqual(env.buffer_s, 4)

    def test_slow_download_causes_rebuffering_after_startup(self):
        env = StreamingEnvironment(
            [2000, 2000, 250],
            StreamingConfig(segment_duration_s=2, startup_buffer_s=4, max_buffer_s=10),
        )
        env.step(1000)
        env.step(1000)
        result = env.step(1000)

        self.assertEqual(result.download_time_s, 8)
        self.assertEqual(result.rebuffering_s, 4)
        self.assertEqual(result.buffer_after_s, 2)

    def test_wait_prevents_buffer_overflow(self):
        env = StreamingEnvironment(
            [10000, 10000, 10000],
            StreamingConfig(segment_duration_s=2, startup_buffer_s=2, max_buffer_s=3),
        )
        env.step(1000)
        second = env.step(1000)

        self.assertAlmostEqual(second.wait_time_s, 1)
        self.assertLessEqual(second.buffer_after_s, 3)

    def test_rejects_invalid_bandwidth(self):
        with self.assertRaises(ValueError):
            StreamingEnvironment([1000, 0])

    def test_manifest_uses_measured_size_and_duration(self):
        entries = [
            SegmentMetadata("video", 0, 500, 2.0, 250000, psnr_y_db=31),
            SegmentMetadata("video", 0, 1000, 2.0, 500000, psnr_y_db=34),
            SegmentMetadata("video", 1, 500, 3.0, 125000, psnr_y_db=30),
            SegmentMetadata("video", 1, 1000, 3.0, 250000, psnr_y_db=33),
        ]
        manifest = SegmentManifest(entries)
        env = StreamingEnvironment(
            [1000, 1000],
            StreamingConfig(segment_duration_s=2, startup_buffer_s=2, max_buffer_s=10),
            segment_manifest=manifest,
        )

        first = env.step(500)
        second = env.step(500)

        self.assertEqual(first.segment_size_kbits, 2000)
        self.assertEqual(first.download_time_s, 2)
        self.assertEqual(first.segment_size_source, "manifest")
        self.assertEqual(first.psnr_y_db, 31)
        self.assertEqual(second.segment_duration_s, 3)
        self.assertEqual(second.buffer_after_s, 4)
        self.assertEqual(env.summary()["video_duration_s"], 5)

    def test_manifest_rejects_a_longer_bandwidth_trace(self):
        manifest = SegmentManifest(
            [SegmentMetadata("video", 0, 500, 2.0, 125000)]
        )
        with self.assertRaisesRegex(ValueError, "mais segmentos"):
            StreamingEnvironment([1000, 1000], segment_manifest=manifest)


if __name__ == "__main__":
    unittest.main()
