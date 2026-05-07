import unittest

from app.config import TrackerConfig
from app.schemas.detection import BoundingBox, Detection
from app.vision.sort_tracker import SortTracker


def detection(x1: float, y1: float, x2: float, y2: float) -> Detection:
    return Detection(
        bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
        confidence=0.9,
        class_id=0,
    )


class SortTrackerTests(unittest.TestCase):
    def test_keeps_track_id_for_overlapping_detections(self) -> None:
        tracker = SortTracker(TrackerConfig(min_hits=2, iou_threshold=0.3))

        first = tracker.update([detection(0, 0, 10, 10)], frame_index=0, timestamp_s=0.0)
        second = tracker.update([detection(1, 1, 11, 11)], frame_index=1, timestamp_s=1.0)

        self.assertEqual(first[0].track_id, second[0].track_id)
        self.assertFalse(first[0].is_confirmed)
        self.assertTrue(second[0].is_confirmed)

    def test_expires_tracks_after_max_age(self) -> None:
        tracker = SortTracker(TrackerConfig(max_age_frames=0, min_hits=1))

        first = tracker.update([detection(0, 0, 10, 10)], frame_index=0, timestamp_s=0.0)
        tracker.update([], frame_index=1, timestamp_s=1.0)
        second = tracker.update([detection(0, 0, 10, 10)], frame_index=2, timestamp_s=2.0)

        self.assertNotEqual(first[0].track_id, second[0].track_id)


if __name__ == "__main__":
    unittest.main()

