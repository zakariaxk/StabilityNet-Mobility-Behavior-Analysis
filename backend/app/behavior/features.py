"""Temporal behavior feature extraction."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from app.behavior.track_state import TrackHistory, TrackPoint
from app.config import BehaviorConfig


@dataclass(frozen=True)
class BehaviorFeatures:
    track_id: int
    observations: int
    duration_s: float
    dwell_time_s: float
    mean_speed_px_s: float
    recent_speed_px_s: float
    position_variance_px2: float
    is_confirmed: bool

    def to_dict(self) -> dict[str, bool | float | int]:
        return {
            "track_id": self.track_id,
            "observations": self.observations,
            "duration_s": self.duration_s,
            "dwell_time_s": self.dwell_time_s,
            "mean_speed_px_s": self.mean_speed_px_s,
            "recent_speed_px_s": self.recent_speed_px_s,
            "position_variance_px2": self.position_variance_px2,
            "is_confirmed": self.is_confirmed,
        }


def extract_features(history: TrackHistory, config: BehaviorConfig) -> BehaviorFeatures:
    latest_timestamp = history.points[-1].timestamp_s if history.points else 0.0
    window_start = latest_timestamp - config.feature_window_s
    window_points = history.points_since(window_start)

    return BehaviorFeatures(
        track_id=history.track_id,
        observations=len(history.points),
        duration_s=history.duration_s,
        dwell_time_s=_dwell_time(history.points, config.dwell_radius_px),
        mean_speed_px_s=_mean_speed(window_points),
        recent_speed_px_s=_recent_speed(history.points),
        position_variance_px2=_position_variance(window_points),
        is_confirmed=history.is_confirmed,
    )


def _dwell_time(points: list[TrackPoint], radius_px: float) -> float:
    if len(points) < 2:
        return 0.0

    latest = points[-1]
    dwell_start = latest.timestamp_s
    for point in reversed(points):
        if _distance(point.center, latest.center) <= radius_px:
            dwell_start = point.timestamp_s
            continue
        break

    return max(0.0, latest.timestamp_s - dwell_start)


def _mean_speed(points: list[TrackPoint]) -> float:
    if len(points) < 2:
        return 0.0

    duration_s = max(0.0, points[-1].timestamp_s - points[0].timestamp_s)
    if duration_s == 0:
        return 0.0

    distance_px = sum(
        _distance(previous.center, current.center)
        for previous, current in zip(points, points[1:], strict=False)
    )
    return distance_px / duration_s


def _recent_speed(points: list[TrackPoint]) -> float:
    if len(points) < 2:
        return 0.0

    previous = points[-2]
    current = points[-1]
    elapsed_s = max(0.0, current.timestamp_s - previous.timestamp_s)
    if elapsed_s == 0:
        return 0.0
    return _distance(previous.center, current.center) / elapsed_s


def _position_variance(points: list[TrackPoint]) -> float:
    if len(points) < 2:
        return 0.0

    mean_x = sum(point.center[0] for point in points) / len(points)
    mean_y = sum(point.center[1] for point in points) / len(points)
    return sum(
        (point.center[0] - mean_x) ** 2 + (point.center[1] - mean_y) ** 2
        for point in points
    ) / len(points)


def _distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return hypot(left[0] - right[0], left[1] - right[1])

