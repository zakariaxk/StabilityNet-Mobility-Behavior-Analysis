"""Tracking data structures."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.detection import BoundingBox


@dataclass(frozen=True)
class TrackObservation:
    track_id: int
    bbox: BoundingBox
    confidence: float
    frame_index: int
    timestamp_s: float
    is_confirmed: bool

    @property
    def center(self) -> tuple[float, float]:
        return self.bbox.center

    def to_dict(self) -> dict[str, bool | float | int | dict[str, float | list[float]]]:
        center_x, center_y = self.center
        return {
            "track_id": self.track_id,
            "bbox": self.bbox.to_dict(),
            "center": [center_x, center_y],
            "confidence": self.confidence,
            "frame_index": self.frame_index,
            "timestamp_s": self.timestamp_s,
            "is_confirmed": self.is_confirmed,
        }

