import unittest

from app.behavior.features import BehaviorFeatures
from app.behavior.scoring import EventScorer
from app.config import BehaviorConfig
from app.schemas.detection import BoundingBox
from app.schemas.tracking import TrackObservation


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
            recent_vertical_delta_px=18.0,
            vertical_speed_px_s=120.0,
            bbox_height_change_ratio=0.22,
            bbox_width_change_ratio=0.16,
            recent_aspect_ratio=0.55,
            bbox_aspect_ratio_change=0.14,
        )

        observation = TrackObservation(
            track_id=7,
            bbox=BoundingBox(180, 120, 300, 340),
            confidence=0.78,
            frame_index=60,
            timestamp_s=9.0,
            is_confirmed=True,
        )

        events = EventScorer(BehaviorConfig()).score(
            features,
            timestamp_s=9.0,
            observation=observation,
            frame_size=(640, 360),
        )
        self.assertEqual(
            [event.event_type for event in events],
            ["Movement anomaly", "Slow walking", "Fall-like motion event"],
        )
        self.assertEqual(events[1].severity, "normal")
        self.assertEqual(events[2].severity, "high")
        self.assertTrue(all(event.track_id == 7 for event in events))
        self.assertTrue(all(event.feature_snapshot["track_id"] == 7 for event in events))

    def test_high_severity_requires_strong_motion_evidence(self) -> None:
        features = BehaviorFeatures(
            track_id=4,
            observations=16,
            duration_s=4.0,
            dwell_time_s=0.0,
            mean_speed_px_s=50.0,
            recent_speed_px_s=42.0,
            position_variance_px2=1600.0,
            is_confirmed=True,
            recent_aspect_ratio=0.34,
        )

        events = EventScorer(BehaviorConfig()).score(features, timestamp_s=4.0)

        self.assertEqual([event.event_type for event in events], ["Movement anomaly"])
        self.assertEqual(events[0].severity, "review_needed")

    def test_strong_fall_like_event_is_not_suppressed_by_medium_confidence(self) -> None:
        features = BehaviorFeatures(
            track_id=9,
            observations=12,
            duration_s=3.0,
            dwell_time_s=0.0,
            mean_speed_px_s=72.0,
            recent_speed_px_s=12.0,
            position_variance_px2=2600.0,
            is_confirmed=True,
            recent_vertical_delta_px=16.0,
            vertical_speed_px_s=110.0,
            bbox_height_change_ratio=0.18,
            bbox_width_change_ratio=0.12,
            recent_aspect_ratio=0.52,
            bbox_aspect_ratio_change=0.1,
        )
        observation = TrackObservation(
            track_id=9,
            bbox=BoundingBox(200, 160, 320, 360),
            confidence=0.45,
            frame_index=18,
            timestamp_s=2.8,
            is_confirmed=True,
        )

        events = EventScorer(BehaviorConfig()).score(
            features,
            timestamp_s=2.8,
            observation=observation,
            frame_size=(640, 360),
        )

        self.assertEqual([event.event_type for event in events], ["Fall-like motion event"])
        self.assertEqual(events[0].severity, "high")

    def test_ignores_unconfirmed_or_short_tracks(self) -> None:
        scorer = EventScorer(BehaviorConfig(min_track_duration_s=2.0))
        unconfirmed = BehaviorFeatures(1, 4, 5.0, 5.0, 0.0, 0.0, 0.0, False)
        short = BehaviorFeatures(1, 4, 1.0, 5.0, 0.0, 0.0, 0.0, True)

        self.assertEqual(scorer.score(unconfirmed, timestamp_s=5.0), [])
        self.assertEqual(scorer.score(short, timestamp_s=1.0), [])


if __name__ == "__main__":
    unittest.main()
