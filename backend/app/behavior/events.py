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
    confidence: float = 0.0
    display_priority: int = 50
    merged_count: int = 1

    def to_dict(self) -> dict[str, bool | float | int | str | dict[str, bool | float | int]]:
        return {
            "event_id": self.event_id,
            "track_id": self.track_id,
            "time_seconds": self.timestamp_s,
            "event_type": self.event_type,
            "name": self.event_type,
            "description": self.reason,
            "severity": self.severity,
            "score": self.score,
            "confidence": self.confidence,
            "timestamp_s": self.timestamp_s,
            "reason": self.reason,
            "display_priority": self.display_priority,
            "merged_count": self.merged_count,
            "feature_snapshot": self.feature_snapshot,
        }
