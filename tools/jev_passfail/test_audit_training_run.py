import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from audit_training_run import assert_close, check_prediction_rows


class TrainingAuditTests(unittest.TestCase):
    def test_validation_metrics_recompute_from_aligned_predictions(self):
        validation = [
            {
                "state_hash": "a",
                "dataset": "searchqa",
                "task_group": "q1",
                "n_pass": 1,
                "n_fail": 0,
                "n_trials": 1,
            },
            {
                "state_hash": "b",
                "dataset": "searchqa",
                "task_group": "q2",
                "n_pass": 0,
                "n_fail": 1,
                "n_trials": 1,
            },
        ]
        predictions = [
            {**validation[0], "p_fail": 0.2, "p_pass": 0.8},
            {**validation[1], "p_fail": 0.7, "p_pass": 0.3},
        ]
        metrics = check_prediction_rows(predictions, validation, "epoch 1")
        assert_close(metrics, metrics)
        with self.assertRaisesRegex(ValueError, "provenance"):
            check_prediction_rows(
                [{**predictions[0], "n_trials": 2}, predictions[1]], validation, "epoch 1"
            )

    def test_nested_metric_audit_finds_a_changed_number(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            assert_close({"overall": {"nll": 0.5}}, {"overall": {"nll": 0.6}})


if __name__ == "__main__":
    unittest.main()
