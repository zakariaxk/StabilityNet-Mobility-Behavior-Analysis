"""Lightweight SORT-style tracker.

This implementation uses SORT's practical lifecycle concepts with greedy IoU
association. It intentionally avoids extra dependencies until the project has
video outputs that justify a full Kalman/Hungarian implementation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import TrackerConfig
from app.schemas.detection import BoundingBox, Detection
from app.schemas.tracking import TrackObservation
from app.utils.geometry import bbox_iou


@dataclass
class _TrackedObject:
    track_id: int
    bbox: BoundingBox
    confidence: float
    hits: int
    missed_frames: int

    @property
    def is_confirmed(self) -> bool:
        return self.hits >= 1

    def update(self, detection: Detection) -> None:
        self.bbox = detection.bbox
        self.confidence = detection.confidence
        self.hits += 1
        self.missed_frames = 0

    def mark_missed(self) -> None:
        self.missed_frames += 1


class SortTracker:
    """Assign stable track IDs to per-frame detections."""

    def __init__(self, config: TrackerConfig) -> None:
        self.config = config
        self._tracks: dict[int, _TrackedObject] = {}
        self._next_track_id = 1

    def update(
        self,
        detections: list[Detection],
        frame_index: int,
        timestamp_s: float,
    ) -> list[TrackObservation]:
        matches, unmatched_track_ids, unmatched_detection_indices = self._match(detections)
        observations: list[TrackObservation] = []

        for track_id, detection_index in matches:
            track = self._tracks[track_id]
            track.update(detections[detection_index])
            observations.append(self._to_observation(track, frame_index, timestamp_s))

        for detection_index in unmatched_detection_indices:
            track = self._create_track(detections[detection_index])
            observations.append(self._to_observation(track, frame_index, timestamp_s))

        for track_id in unmatched_track_ids:
            self._tracks[track_id].mark_missed()

        self._drop_expired_tracks()
        return observations

    def _match(self, detections: list[Detection]) -> tuple[list[tuple[int, int]], set[int], set[int]]:
        if not self._tracks:
            return [], set(), set(range(len(detections)))
        if not detections:
            return [], set(self._tracks), set()

        candidate_pairs: list[tuple[float, int, int]] = []
        for track_id, track in self._tracks.items():
            for detection_index, detection in enumerate(detections):
                score = bbox_iou(track.bbox, detection.bbox)
                if score >= self.config.iou_threshold:
                    candidate_pairs.append((score, track_id, detection_index))

        candidate_pairs.sort(reverse=True)
        used_tracks: set[int] = set()
        used_detections: set[int] = set()
        matches: list[tuple[int, int]] = []

        for _score, track_id, detection_index in candidate_pairs:
            if track_id in used_tracks or detection_index in used_detections:
                continue
            used_tracks.add(track_id)
            used_detections.add(detection_index)
            matches.append((track_id, detection_index))

        unmatched_track_ids = set(self._tracks) - used_tracks
        unmatched_detection_indices = set(range(len(detections))) - used_detections
        return matches, unmatched_track_ids, unmatched_detection_indices

    def _create_track(self, detection: Detection) -> _TrackedObject:
        track = _TrackedObject(
            track_id=self._next_track_id,
            bbox=detection.bbox,
            confidence=detection.confidence,
            hits=1,
            missed_frames=0,
        )
        self._tracks[track.track_id] = track
        self._next_track_id += 1
        return track

    def _drop_expired_tracks(self) -> None:
        expired_ids = [
            track_id
            for track_id, track in self._tracks.items()
            if track.missed_frames > self.config.max_age_frames
        ]
        for track_id in expired_ids:
            del self._tracks[track_id]

    def _to_observation(
        self,
        track: _TrackedObject,
        frame_index: int,
        timestamp_s: float,
    ) -> TrackObservation:
        return TrackObservation(
            track_id=track.track_id,
            bbox=track.bbox,
            confidence=track.confidence,
            frame_index=frame_index,
            timestamp_s=timestamp_s,
            is_confirmed=track.hits >= self.config.min_hits,
        )

