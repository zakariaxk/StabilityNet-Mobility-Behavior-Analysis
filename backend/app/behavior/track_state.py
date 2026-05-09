"""Per-track temporal state."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.tracking import TrackObservation


@dataclass(frozen=True)
class TrackPoint:
    track_id: int
    frame_index: int
    timestamp_s: float
    center: tuple[float, float]
    confidence: float
    bbox_width: float
    bbox_height: float
    is_confirmed: bool


@dataclass
class TrackHistory:
    track_id: int
    points: list[TrackPoint] = field(default_factory=list)

    def add(self, observation: TrackObservation) -> TrackPoint:
        point = TrackPoint(
            track_id=observation.track_id,
            frame_index=observation.frame_index,
            timestamp_s=observation.timestamp_s,
            center=observation.center,
            confidence=observation.confidence,
            bbox_width=observation.bbox.width,
            bbox_height=observation.bbox.height,
            is_confirmed=observation.is_confirmed,
        )
        self.points.append(point)
        return point

    @property
    def duration_s(self) -> float:
        if len(self.points) < 2:
            return 0.0
        return max(0.0, self.points[-1].timestamp_s - self.points[0].timestamp_s)

    @property
    def is_confirmed(self) -> bool:
        return any(point.is_confirmed for point in self.points)

    def points_since(self, timestamp_s: float) -> list[TrackPoint]:
        return [point for point in self.points if point.timestamp_s >= timestamp_s]


class TrackStore:
    """Mutable store of track histories keyed by tracker ID."""

    def __init__(self) -> None:
        self._histories: dict[int, TrackHistory] = {}

    def update(self, observation: TrackObservation) -> TrackHistory:
        history = self._histories.setdefault(
            observation.track_id,
            TrackHistory(track_id=observation.track_id),
        )
        history.add(observation)
        return history

    def all_histories(self) -> list[TrackHistory]:
        return list(self._histories.values())
