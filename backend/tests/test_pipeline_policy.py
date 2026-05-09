import unittest

from app.behavior.events import BehaviorEvent
from app.behavior.features import BehaviorFeatures
from app.config import BehaviorConfig
from app.pipeline.video_pipeline import (
    _display_events,
    _merge_nearby_events,
    _scene_reliability,
    _summarize_tracks,
    _track_end_events,
)
from app.schemas.detection import BoundingBox
from app.schemas.tracking import TrackObservation


def observation(
    track_id: int,
    frame_index: int,
    timestamp_s: float,
    bbox: BoundingBox | None = None,
    *,
    confidence: float = 0.8,
    confirmed: bool = True,
) -> TrackObservation:
    return TrackObservation(
        track_id=track_id,
        bbox=bbox or BoundingBox(100, 100, 150, 220),
        confidence=confidence,
        frame_index=frame_index,
        timestamp_s=timestamp_s,
        is_confirmed=confirmed,
    )


def event(
    event_type: str,
    severity: str,
    *,
    track_id: int = 1,
    timestamp_s: float = 1.0,
) -> BehaviorEvent:
    return BehaviorEvent(
        event_id=f"{track_id}-{event_type}-{timestamp_s}",
        track_id=track_id,
        event_type=event_type,
        severity=severity,
        score=0.8 if severity == "high" else 0.2,
        timestamp_s=timestamp_s,
        reason="test event",
        feature_snapshot={"track_id": track_id},
    )


class PipelinePolicyTests(unittest.TestCase):
    def test_ultra_short_tracks_are_not_qualified_subjects(self) -> None:
        observations = [
            observation(1, index, index / 30.0)
            for index in range(5)
        ]

        tracks = _summarize_tracks(
            observations,
            {},
            frame_width=640,
            frame_height=360,
            config=BehaviorConfig(min_track_duration_s=1.0, min_track_frames=10),
        )

        self.assertEqual(len(tracks), 1)
        self.assertFalse(tracks[0]["qualified"])
        self.assertIn("track_too_short", str(tracks[0]["suppression_reason"]))

    def test_track_ending_near_boundary_is_not_high_instability(self) -> None:
        previous = observation(3, 10, 1.0, BoundingBox(620, 100, 638, 220))

        events = _track_end_events(
            previous_observations={3: previous},
            current_observations=[],
            latest_features={},
            frame_width=640,
            frame_height=360,
            timestamp_s=1.1,
        )

        self.assertEqual(events[0].event_type, "Subject leaving frame")
        self.assertEqual(events[0].severity, "review_needed")

    def test_insufficient_evidence_is_not_labeled_low(self) -> None:
        tracks = [
            {
                "track_id": 1,
                "qualified": False,
                "avg_confidence": 0.3,
            }
        ]

        display_events, _suppressed = _display_events(
            events=[event("Insufficient visual evidence", "low")],
            tracks=tracks,
            scene_reliability={"category": "High", "score": 1.0, "reasons": []},
        )

        self.assertEqual(display_events[0].severity, "insufficient_evidence")

    def test_event_cooldown_merges_nearby_repeated_events(self) -> None:
        merged = _merge_nearby_events(
            [
                event("Camera motion uncertainty", "review_needed", track_id=-1, timestamp_s=1.0),
                event("Camera motion uncertainty", "review_needed", track_id=-1, timestamp_s=2.0),
            ]
        )

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].merged_count, 2)

    def test_scene_reliability_low_for_fragmented_crowded_scene(self) -> None:
        tracks = [
            {"track_id": index, "qualified": index < 4}
            for index in range(30)
        ]

        reliability = _scene_reliability(
            tracks=tracks,
            raw_events=[event("Camera motion uncertainty", "review_needed", track_id=-1)],
            frames_processed=400,
        )

        self.assertEqual(reliability["category"], "Low")
        self.assertIn("high track fragmentation", reliability["reasons"])

    def test_low_reliability_downgrades_non_fall_high_events(self) -> None:
        tracks = [{"track_id": 1, "qualified": True, "avg_confidence": 0.9}]

        display_events, _suppressed = _display_events(
            events=[event("Abrupt trajectory change", "high")],
            tracks=tracks,
            scene_reliability={"category": "Low", "score": 0.3, "reasons": []},
        )

        self.assertEqual(display_events[0].severity, "review_needed")


if __name__ == "__main__":
    unittest.main()
