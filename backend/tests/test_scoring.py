import unittest

from app.behavior.features import BehaviorFeatures
from app.behavior.scoring import EventScorer
from app.config import BehaviorConfig


class EventScoringTests(unittest.TestCase):
    def test_scores_conservative_threshold_crossings(self) -> None:
        features = BehaviorFeatures(
            track_id=7,
            observations=16,
            duration_s=13.0,
            dwell_time_s=13.0,
            mean_speed_px_s=5.0,
            recent_speed_px_s=0.0,
            position_variance_px2=1600.0,
            is_confirmed=True,
            recent_vertical_delta_px=35.0,
            bbox_height_change_ratio=0.35,
        )

        events = EventScorer(BehaviorConfig()).score(features, timestamp_s=9.0)

        self.assertEqual(
            [event.event_type for event in events],
            ["Movement anomaly", "Slow walking", "Fall-like motion event"],
        )
        self.assertEqual(events[1].severity, "normal")
        self.assertEqual(events[2].severity, "high")
        self.assertTrue(all(event.track_id == 7 for event in events))
        self.assertTrue(all(event.feature_snapshot["track_id"] == 7 for event in events))

    def test_high_severity_requires_strong_motion_evidence(self) -> None:
        # Brisk steady walking: variance=1600 is below the new 2.8x review threshold (2520),
        # no fall signals, no deceleration pattern → no events emitted.
        features = BehaviorFeatures(
            track_id=4,
            observations=16,
            duration_s=4.0,
            dwell_time_s=0.0,
            mean_speed_px_s=50.0,
            recent_speed_px_s=42.0,
            position_variance_px2=1600.0,
            is_confirmed=True,
        )

        events = EventScorer(BehaviorConfig()).score(features, timestamp_s=4.0)

        self.assertEqual(events, [])

    def test_ignores_unconfirmed_or_short_tracks(self) -> None:
        scorer = EventScorer(BehaviorConfig(min_track_duration_s=2.0))
        unconfirmed = BehaviorFeatures(1, 4, 5.0, 5.0, 0.0, 0.0, 0.0, False)
        short = BehaviorFeatures(1, 4, 1.0, 5.0, 0.0, 0.0, 0.0, True)

        self.assertEqual(scorer.score(unconfirmed, timestamp_s=5.0), [])
        self.assertEqual(scorer.score(short, timestamp_s=1.0), [])


if __name__ == "__main__":
    unittest.main()
