"""Behavior event data structures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BehaviorEvent:
    event_id: str
    track_id: int
    event_type: str
    severity: str
    score: float
    timestamp_s: float
    reason: str
    feature_snapshot: dict[str, bool | float | int]

    def to_dict(self) -> dict[str, bool | float | int | str | dict[str, bool | float | int]]:
        return {
            "event_id": self.event_id,
            "track_id": self.track_id,
            "event_type": self.event_type,
            "severity": self.severity,
            "score": self.score,
            "timestamp_s": self.timestamp_s,
            "reason": self.reason,
            "feature_snapshot": self.feature_snapshot,
        }

