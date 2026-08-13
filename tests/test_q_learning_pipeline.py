import unittest

import numpy as np

from experiment import ExperimentConfig
from q_learning_pipeline import (
    RewardConfig,
    StateEncoder,
    TrainingConfig,
    calculate_reward,
    run_q_learning_experiment,
    train_q_learning,
)
from streaming_env import SegmentResult


class QLearningPipelineTest(unittest.TestCase):
    def test_encoder_reserves_state_for_unknown_throughput(self):
        encoder = StateEncoder([500, 1000, 2000], [2, 4, 8])
        unknown = encoder.encode(0, 500, None)
        measured = encoder.encode(0, 500, 1500)

        self.assertNotEqual(unknown, measured)
        self.assertGreaterEqual(unknown, 0)
        self.assertLess(unknown, encoder.num_states)

    def test_reward_penalizes_rebuffering(self):
        base = dict(
            segment=0,
            bitrate_kbps=1000,
            bandwidth_kbps=1000,
            segment_size_kbits=2000,
            download_time_s=2,
            startup_delay_s=0,
            wait_time_s=0,
            buffer_before_s=4,
            buffer_after_s=4,
            playback_started=True,
        )
        clean = SegmentResult(**base, rebuffering_s=0)
        stalled = SegmentResult(**base, rebuffering_s=2)
        config = RewardConfig()

        clean_reward = calculate_reward(clean, 1000, 500, 2000, 2, config)
        stalled_reward = calculate_reward(stalled, 1000, 500, 2000, 2, config)
        self.assertGreater(clean_reward.reward, stalled_reward.reward)

    def test_reward_penalizes_startup_when_weight_is_enabled(self):
        base = dict(
            segment=0,
            bitrate_kbps=1000,
            bandwidth_kbps=1000,
            segment_size_kbits=2000,
            download_time_s=2,
            wait_time_s=0,
            buffer_before_s=0,
            buffer_after_s=2,
            rebuffering_s=0,
            playback_started=False,
        )
        immediate = SegmentResult(**base, startup_delay_s=0)
        delayed = SegmentResult(**base, startup_delay_s=2)
        config = RewardConfig(startup_weight=0.5)

        immediate_reward = calculate_reward(
            immediate, 1000, 500, 2000, 2, config
        )
        delayed_reward = calculate_reward(
            delayed, 1000, 500, 2000, 2, config
        )

        self.assertEqual(immediate_reward.startup_penalty, 0)
        self.assertEqual(delayed_reward.startup_penalty, 0.5)
        self.assertAlmostEqual(
            immediate_reward.reward - delayed_reward.reward,
            0.5,
        )

    def test_training_is_reproducible_and_evaluable(self):
        experiment = ExperimentConfig(
            bitrates_kbps=(500, 1000, 2000),
            segment_duration_s=2,
            startup_buffer_s=2,
            max_buffer_s=10,
            seed=17,
        )
        training = TrainingConfig(
            episodes=30,
            epsilon_decay=0.9,
            epsilon_min=0.05,
            buffer_boundaries_s=(2, 4, 8),
            seed=17,
        )
        traces = [("train", [3000, 2500, 800, 500, 1200, 3000])]

        first = train_q_learning(traces, experiment, training, RewardConfig())
        second = train_q_learning(traces, experiment, training, RewardConfig())
        agent, encoder, history, _ = first

        np.testing.assert_array_equal(agent.q_table, second[0].q_table)
        self.assertTrue(np.any(agent.q_table != 0))
        self.assertEqual(len(history), 30)
        self.assertEqual(agent.epsilon, 0.05)

        rows, summary = run_q_learning_experiment(
            traces[0][1],
            experiment,
            agent,
            encoder,
            RewardConfig(),
        )
        self.assertEqual(len(rows), 6)
        self.assertEqual(summary["controller"], "q-learning")
        self.assertIn("reward", rows[0])


if __name__ == "__main__":
    unittest.main()
