import json
import tempfile
import unittest
from pathlib import Path

from trace_synthesis import (
    generate_trace,
    generate_trace_suite,
    load_trace_synthesis_definition,
)


class TraceSynthesisTest(unittest.TestCase):
    def _configuration(self, root: Path) -> Path:
        path = root / "traces.json"
        path.write_text(
            json.dumps(
                {
                    "generator_version": 1,
                    "model": {
                        "segments": 8,
                        "regime_means_kbps": [500, 2000],
                        "transition_matrix": [[0.8, 0.2], [0.2, 0.8]],
                        "autoregressive_alpha": 0.5,
                        "log_noise_sigma": 0.1,
                        "minimum_kbps": 300,
                        "maximum_kbps": 3000,
                    },
                    "traces": [
                        {
                            "id": "validation",
                            "split": "validation",
                            "seed": 10,
                            "initial_regime": 0,
                            "path": "validation.csv",
                        },
                        {
                            "id": "evaluation",
                            "split": "evaluation",
                            "seed": 20,
                            "initial_regime": 1,
                            "path": "evaluation.csv",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_generation_is_reproducible_and_splits_are_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            definition = load_trace_synthesis_definition(
                self._configuration(root)
            )
            first = generate_trace(definition.model, definition.traces[0])
            repeated = generate_trace(definition.model, definition.traces[0])
            evaluation = generate_trace(definition.model, definition.traces[1])

            self.assertEqual(first, repeated)
            self.assertNotEqual(first, evaluation)
            self.assertTrue(all(300 <= value <= 3000 for value in first))

            outputs = generate_trace_suite(
                definition,
                root / "provenance.json",
            )
            self.assertTrue(all(path.is_file() for path in outputs.values()))
            with self.assertRaises(FileExistsError):
                generate_trace_suite(
                    definition,
                    root / "provenance.json",
                )


if __name__ == "__main__":
    unittest.main()
