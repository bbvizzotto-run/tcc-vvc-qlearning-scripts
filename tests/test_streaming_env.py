import unittest

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


if __name__ == "__main__":
    unittest.main()
