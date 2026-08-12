import unittest

from controllers import StaticThresholdController


class StaticThresholdControllerTest(unittest.TestCase):
    def test_increases_maintains_and_decreases_one_level(self):
        controller = StaticThresholdController([500, 1000, 2000], 4, 10)

        self.assertEqual(controller.select_bitrate(12).bitrate_kbps, 1000)
        self.assertEqual(controller.select_bitrate(7).bitrate_kbps, 1000)
        decision = controller.select_bitrate(2)

        self.assertEqual(decision.bitrate_kbps, 500)
        self.assertEqual(decision.action, "decrease")

    def test_never_exceeds_ladder(self):
        controller = StaticThresholdController([500, 1000], 4, 10)
        for _ in range(5):
            decision = controller.select_bitrate(20)
        self.assertEqual(decision.bitrate_kbps, 1000)


if __name__ == "__main__":
    unittest.main()
