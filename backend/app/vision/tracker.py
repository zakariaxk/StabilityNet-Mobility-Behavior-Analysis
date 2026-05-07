"""Tracker interfaces."""

from __future__ import annotations

from typing import Protocol

from app.schemas.detection import Detection
from app.schemas.tracking import TrackObservation


class MultiObjectTracker(Protocol):
    def update(
        self,
        detections: list[Detection],
        frame_index: int,
        timestamp_s: float,
    ) -> list[TrackObservation]:
        """Update tracker state and return observations for this frame."""

