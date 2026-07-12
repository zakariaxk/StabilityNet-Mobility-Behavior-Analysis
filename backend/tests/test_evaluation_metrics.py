import unittest

from app.evaluation.metrics import EvaluationEvent, evaluate_events


class EventEvaluationTests(unittest.TestCase):
    def test_matches_events_by_type_track_and_temporal_tolerance(self) -> None:
        ground_truth = [
            EvaluationEvent("Fall-like motion event", 1, 10.0),
            EvaluationEvent("Postural Transition", 2, 20.0),
        ]
        predictions = [
            EvaluationEvent("Fall-like motion event", 1, 10.4),
            EvaluationEvent("Postural Transition", 2, 24.0),
            EvaluationEvent("Abrupt trajectory change", 3, 30.0),
        ]

        metrics = evaluate_events(
            ground_truth,
            predictions,
            duration_s=120.0,
            tolerance_s=1.0,
        )

        self.assertEqual(metrics.true_positives, 1)
        self.assertEqual(metrics.false_positives, 2)
        self.assertEqual(metrics.false_negatives, 1)
        self.assertAlmostEqual(metrics.precision, 1 / 3)
        self.assertAlmostEqual(metrics.recall, 0.5)
        self.assertAlmostEqual(metrics.f1, 0.4)
        self.assertAlmostEqual(metrics.false_alarms_per_minute, 1.0)
        self.assertAlmostEqual(metrics.mean_absolute_timing_error_s or 0.0, 0.4)

    def test_matching_is_one_to_one_and_uses_nearest_prediction(self) -> None:
        ground_truth = [EvaluationEvent("Fall-like motion event", 1, 10.0)]
        predictions = [
            EvaluationEvent("Fall-like motion event", 1, 9.5),
            EvaluationEvent("Fall-like motion event", 1, 10.1),
        ]

        metrics = evaluate_events(ground_truth, predictions, duration_s=60.0)

        self.assertEqual(metrics.true_positives, 1)
        self.assertEqual(metrics.false_positives, 1)
        self.assertAlmostEqual(metrics.mean_absolute_timing_error_s or 0.0, 0.1)

    def test_zero_event_clip_has_defined_non_misleading_metrics(self) -> None:
        metrics = evaluate_events([], [], duration_s=30.0)

        self.assertEqual(metrics.precision, 1.0)
        self.assertEqual(metrics.recall, 1.0)
        self.assertEqual(metrics.f1, 1.0)
        self.assertIsNone(metrics.mean_absolute_timing_error_s)

    def test_rejects_invalid_duration_and_tolerance(self) -> None:
        with self.assertRaisesRegex(ValueError, "duration_s"):
            evaluate_events([], [], duration_s=0.0)
        with self.assertRaisesRegex(ValueError, "tolerance_s"):
            evaluate_events([], [], duration_s=1.0, tolerance_s=-1.0)


if __name__ == "__main__":
    unittest.main()
