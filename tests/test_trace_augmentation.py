import unittest

from trace_augmentation import TraceAugmentationConfig, augment_bandwidth_trace


class TraceAugmentationTest(unittest.TestCase):
    def test_is_reproducible_and_does_not_mutate_source(self):
        source = [1000.0, 2000.0, 3000.0, 4000.0]
        original = source.copy()
        config = TraceAugmentationConfig()

        first = augment_bandwidth_trace(source, config, seed=17)
        second = augment_bandwidth_trace(source, config, seed=17)

        self.assertEqual(first, second)
        self.assertEqual(source, original)
        self.assertNotEqual(first, original)
        self.assertTrue(all(value >= config.min_bandwidth_kbps for value in first))

    def test_probability_zero_preserves_trace(self):
        source = [500.0, 1000.0, 2000.0]
        config = TraceAugmentationConfig(apply_probability=0)

        self.assertEqual(
            augment_bandwidth_trace(source, config, seed=9),
            source,
        )

    def test_forced_burst_creates_a_short_drop(self):
        source = [2000.0] * 8
        config = TraceAugmentationConfig(
            scale_min=1,
            scale_max=1,
            jitter_fraction=0,
            circular_shift=False,
            burst_probability=1,
            burst_count_min=1,
            burst_count_max=1,
            burst_length_min=2,
            burst_length_max=2,
            burst_factor_min=0.1,
            burst_factor_max=0.1,
            min_bandwidth_kbps=250,
        )

        augmented = augment_bandwidth_trace(source, config, seed=5)

        self.assertIn(250, augmented)
        self.assertIn(2000, augmented)


if __name__ == "__main__":
    unittest.main()
