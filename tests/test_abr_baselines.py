import unittest

from abr_baselines import (
    BolaConfig,
    BolaController,
    RobustMpcConfig,
    RobustMpcController,
    ThroughputConfig,
    ThroughputController,
)
from q_learning_pipeline import RewardConfig
from streaming_env import SegmentResult, StreamingConfig


def observed_result(bandwidth_kbps: float) -> SegmentResult:
    size_kbits = 1000.0
    return SegmentResult(
        segment=0,
        bitrate_kbps=500,
        bandwidth_kbps=bandwidth_kbps,
        segment_size_kbits=size_kbits,
        download_time_s=size_kbits / bandwidth_kbps,
        startup_delay_s=0,
        wait_time_s=0,
        buffer_before_s=4,
        buffer_after_s=4,
        rebuffering_s=0,
        playback_started=True,
        segment_duration_s=2,
    )


class AbrBaselinesTest(unittest.TestCase):
    def test_throughput_uses_only_completed_downloads_and_safety_margin(self):
        controller = ThroughputController(
            [500, 1000, 2000, 4000],
            ThroughputConfig(history_window=2, safety_factor=0.85),
        )

        self.assertEqual(controller.select_bitrate().bitrate_kbps, 500)
        controller.observe(observed_result(3000))
        self.assertEqual(controller.select_bitrate().bitrate_kbps, 2000)
        controller.observe(observed_result(1000))
        self.assertEqual(controller.select_bitrate().bitrate_kbps, 1000)

    def test_bola_moves_from_low_at_empty_buffer_to_high_at_target(self):
        controller = BolaController(
            [500, 1000, 2000],
            BolaConfig(minimum_buffer_s=4, buffer_target_s=10),
        )

        self.assertEqual(controller.select_bitrate(0).bitrate_kbps, 500)
        self.assertEqual(controller.select_bitrate(10).bitrate_kbps, 2000)

    def test_robust_mpc_corrects_harmonic_prediction_by_worst_error(self):
        controller = RobustMpcController(
            [500, 2000],
            StreamingConfig(segment_duration_s=2, startup_buffer_s=2, max_buffer_s=10),
            RewardConfig(target_buffer_s=4),
            config=RobustMpcConfig(horizon=1, history_window=5, error_window=5),
        )

        first = controller.select_bitrate(0, 0, False, 3)
        self.assertEqual(first.bitrate_kbps, 500)
        controller.observe(observed_result(4000))
        second = controller.select_bitrate(8, 1, True, 2)
        self.assertEqual(second.bitrate_kbps, 2000)
        controller.observe(observed_result(1000))

        # média harmônica(4000, 1000)=1600; pior erro=3; previsão=400.
        self.assertAlmostEqual(controller.predicted_throughput_kbps, 400)

    def test_robust_mpc_forecast_accounts_for_startup_penalty(self):
        controller = RobustMpcController(
            [500, 2000],
            StreamingConfig(
                segment_duration_s=2,
                startup_buffer_s=2,
                max_buffer_s=10,
            ),
            RewardConfig(startup_weight=1, target_buffer_s=4),
            config=RobustMpcConfig(horizon=1),
        )

        low = controller._sequence_reward((500,), 0, 0, False, 1000)
        high = controller._sequence_reward((2000,), 0, 0, False, 1000)

        self.assertGreater(low, high)

    def test_frozen_configs_reject_invalid_parameters(self):
        with self.assertRaises(ValueError):
            ThroughputConfig(history_window=0)
        with self.assertRaises(ValueError):
            BolaConfig(minimum_buffer_s=10, buffer_target_s=10)
        with self.assertRaises(ValueError):
            RobustMpcConfig(horizon=0)


if __name__ == "__main__":
    unittest.main()
