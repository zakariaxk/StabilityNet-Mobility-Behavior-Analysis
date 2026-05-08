import unittest

from app.behavior.features import BehaviorFeatures
from app.behavior.scoring import EventScorer
from app.config import BehaviorConfig


class EventScoringTests(unittest.TestCase):
    def test_scores_threshold_crossings(self) -> None:
        features = BehaviorFeatures(
            track_id=7,
            observations=10,
            duration_s=9.0,
            dwell_time_s=9.0,
            mean_speed_px_s=5.0,
            recent_speed_px_s=0.0,
            position_variance_px2=1000.0,
            is_confirmed=True,
        )

        events = EventScorer(BehaviorConfig()).score(features, timestamp_s=9.0)

        self.assertEqual(
            [event.event_type for event in events],
            ["Prolonged Stop", "Slow Walking", "Tracking Instability"],
        )
        self.assertEqual(events[1].reason, "Reduced movement speed detected.")
        self.assertTrue(all(event.track_id == 7 for event in events))
        self.assertTrue(all(event.feature_snapshot["track_id"] == 7 for event in events))

    def test_ignores_unconfirmed_or_short_tracks(self) -> None:
        scorer = EventScorer(BehaviorConfig(min_track_duration_s=2.0))
        unconfirmed = BehaviorFeatures(1, 4, 5.0, 5.0, 0.0, 0.0, 0.0, False)
        short = BehaviorFeatures(1, 4, 1.0, 5.0, 0.0, 0.0, 0.0, True)

        self.assertEqual(scorer.score(unconfirmed, timestamp_s=5.0), [])
        self.assertEqual(scorer.score(short, timestamp_s=1.0), [])


if __name__ == "__main__":
    unittest.main()
