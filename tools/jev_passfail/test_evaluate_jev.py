import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evaluate_jev import validate_predictions, verify_frozen_run


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.entries = [
            {"row": {"state_hash": "state-a"}},
            {"row": {"state_hash": "state-b"}},
        ]
        self.predictions = [
            {"state_hash": "state-a", "p_fail": 0.25, "p_pass": 0.75},
            {"state_hash": "state-b", "p_fail": 0.6, "p_pass": 0.4},
        ]

    def test_predictions_must_cover_each_unique_input_with_a_distribution(self):
        validate_predictions(self.predictions, self.entries)
        with self.assertRaisesRegex(ValueError, "match"):
            validate_predictions(self.predictions[:1], self.entries)
        with self.assertRaisesRegex(ValueError, "unnormalized"):
            validate_predictions(
                [{**self.predictions[0], "p_pass": 0.7}, self.predictions[1]],
                self.entries,
            )

    def test_test_evaluation_requires_a_frozen_training_run(self):
        with self.assertRaisesRegex(RuntimeError, "completed run"):
            verify_frozen_run(Path("/not/a/completed/run"))


if __name__ == "__main__":
    unittest.main()
