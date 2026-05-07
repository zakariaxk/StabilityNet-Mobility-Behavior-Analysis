import unittest

from app.behavior.features import extract_features
from app.behavior.track_state import TrackHistory
from app.config import BehaviorConfig
from app.schemas.detection import BoundingBox
from app.schemas.tracking import TrackObservation


def observation(
    track_id: int,
    center_x: float,
    center_y: float,
    timestamp_s: float,
    frame_index: int,
    is_confirmed: bool = True,
) -> TrackObservation:
    return TrackObservation(
        track_id=track_id,
        bbox=BoundingBox(center_x - 5, center_y - 5, center_x + 5, center_y + 5),
        confidence=0.9,
        frame_index=frame_index,
        timestamp_s=timestamp_s,
        is_confirmed=is_confirmed,
    )


class FeatureExtractionTests(unittest.TestCase):
    def test_extracts_speed_dwell_and_variance(self) -> None:
        history = TrackHistory(track_id=1)
        history.add(observation(1, 0, 0, 0.0, 0))
        history.add(observation(1, 3, 4, 1.0, 1))
        history.add(observation(1, 6, 8, 2.0, 2))

        features = extract_features(history, BehaviorConfig(dwell_radius_px=20))

        self.assertEqual(features.track_id, 1)
        self.assertEqual(features.observations, 3)
        self.assertAlmostEqual(features.duration_s, 2.0)
        self.assertAlmostEqual(features.mean_speed_px_s, 5.0)
        self.assertAlmostEqual(features.recent_speed_px_s, 5.0)
        self.assertAlmostEqual(features.dwell_time_s, 2.0)
        self.assertAlmostEqual(features.position_variance_px2, 50.0 / 3.0)

    def test_dwell_time_resets_after_leaving_radius(self) -> None:
        history = TrackHistory(track_id=1)
        history.add(observation(1, 0, 0, 0.0, 0))
        history.add(observation(1, 100, 0, 1.0, 1))
        history.add(observation(1, 101, 0, 2.0, 2))

        features = extract_features(history, BehaviorConfig(dwell_radius_px=5))

        self.assertAlmostEqual(features.dwell_time_s, 1.0)


if __name__ == "__main__":
    unittest.main()

