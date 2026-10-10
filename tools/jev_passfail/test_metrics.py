import math
import random
import unittest

from metrics import (
    bootstrap_confidence_intervals,
    compute_metrics,
    resample_task_groups,
)


class MetricTests(unittest.TestCase):
    def test_hand_computable_fractional_metrics(self):
        rows = [
            {
                "dataset": "searchqa",
                "task_group": "q1",
                "p_pass": 0.8,
                "n_pass": 3,
                "n_fail": 1,
                "n_trials": 4,
            },
            {
                "dataset": "searchqa",
                "task_group": "q2",
                "p_pass": 0.2,
                "n_pass": 1,
                "n_fail": 3,
                "n_trials": 4,
            },
        ]
        result = compute_metrics(rows)
        expected_nll = -0.75 * math.log(0.8) - 0.25 * math.log(0.2)
        self.assertAlmostEqual(result["nll"], expected_nll)
        self.assertAlmostEqual(result["brier"], 0.0025)
        self.assertAlmostEqual(result["ece"], 0.05)
        self.assertAlmostEqual(result["balanced_accuracy"], 0.75)
        self.assertAlmostEqual(result["fail_recall"], 0.75)
        self.assertAlmostEqual(result["expected_macro_f1"], 0.75)
        self.assertEqual(result["fractional_confusion"], {
            "true_pass_pred_pass": 3.0,
            "true_fail_pred_pass": 1.0,
            "true_pass_pred_fail": 1.0,
            "true_fail_pred_fail": 3.0,
        })

    def test_half_probability_is_predicted_pass(self):
        result = compute_metrics([{
            "dataset": "alfworld",
            "task_group": "g1",
            "p_pass": 0.5,
            "n_pass": 1,
            "n_fail": 1,
            "n_trials": 2,
        }])
        self.assertEqual(result["fractional_confusion"]["true_pass_pred_pass"], 1.0)
        self.assertEqual(result["fractional_confusion"]["true_fail_pred_pass"], 1.0)

    def test_cluster_bootstrap_preserves_dataset_trial_mix_and_seed(self):
        rows = [
            {"dataset": "searchqa", "task_group": "q1", "p_pass": 0.7, "n_pass": 2, "n_fail": 0, "n_trials": 2},
            {"dataset": "searchqa", "task_group": "q2", "p_pass": 0.3, "n_pass": 1, "n_fail": 5, "n_trials": 6},
            {"dataset": "alfworld", "task_group": "a1", "p_pass": 0.8, "n_pass": 5, "n_fail": 3, "n_trials": 8},
        ]
        sample_a = resample_task_groups(rows, random.Random(17))
        sample_b = resample_task_groups(rows, random.Random(17))
        self.assertEqual(sample_a, sample_b)
        trial_mix = {}
        for row in sample_a:
            ds = row["dataset"]
            trial_mix[ds] = trial_mix.get(ds, 0.0) + row["n_trials"] * row["_bootstrap_multiplier"]
        self.assertAlmostEqual(trial_mix["searchqa"], 8.0)
        self.assertAlmostEqual(trial_mix["alfworld"], 8.0)
        ci_a = bootstrap_confidence_intervals(rows, replicates=25, seed=20260929)
        ci_b = bootstrap_confidence_intervals(rows, replicates=25, seed=20260929)
        self.assertEqual(ci_a, ci_b)
        self.assertEqual(ci_a["replicates"], 25)


if __name__ == "__main__":
    unittest.main()
