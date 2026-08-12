import tempfile
import unittest
from pathlib import Path

import numpy as np

from q_learning_agent import QLearningAgent


class QLearningAgentTest(unittest.TestCase):
    def test_greedy_tie_breaking_is_not_biased_to_action_zero(self):
        agent = QLearningAgent(2, 3, epsilon=0, epsilon_min=0, seed=11)
        actions = {agent.choose_action(0, explore=False) for _ in range(100)}
        self.assertEqual(actions, {0, 1, 2})

    def test_terminal_update_does_not_bootstrap(self):
        agent = QLearningAgent(
            2,
            3,
            learning_rate=1,
            discount_factor=0.9,
            epsilon=0,
            epsilon_min=0,
        )
        agent.q_table[1] = [10, 20, 30]
        agent.update_q_table(0, 1, reward=2, next_state_index=1, terminal=True)
        self.assertEqual(agent.q_table[0, 1], 2)

    def test_save_and_load_preserve_model_and_metadata(self):
        agent = QLearningAgent(3, 3, epsilon=0.4, epsilon_min=0.1, seed=5)
        agent.q_table[1, 2] = 7.5
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model"
            agent.save(path, {"experiment": "unit-test"})
            loaded, metadata = QLearningAgent.load(path.with_suffix(".npz"), seed=9)

        np.testing.assert_array_equal(loaded.q_table, agent.q_table)
        self.assertEqual(metadata["experiment"], "unit-test")
        self.assertEqual(loaded.seed, 9)


if __name__ == "__main__":
    unittest.main()
