"""Explainable heuristic event scoring."""

from __future__ import annotations

from app.behavior.events import BehaviorEvent
from app.behavior.features import BehaviorFeatures
from app.config import BehaviorConfig


class EventScorer:
    """Score behavior features against Phase 1 mobility thresholds."""

    def __init__(self, config: BehaviorConfig) -> None:
        self.config = config

    def score(self, features: BehaviorFeatures, timestamp_s: float) -> list[BehaviorEvent]:
        if not features.is_confirmed:
            return []
        if features.duration_s < self.config.min_track_duration_s:
            return []

        events: list[BehaviorEvent] = []
        if features.dwell_time_s >= self.config.dwell_time_threshold_s:
            score = _ratio(features.dwell_time_s, self.config.dwell_time_threshold_s)
            events.append(
                self._event(
                    features,
                    timestamp_s,
                    event_type="Prolonged Stop",
                    score=score,
                    reason="Prolonged stop detected.",
                )
            )

        if features.mean_speed_px_s <= self.config.slow_speed_threshold_px_s:
            score = _inverse_ratio(
                features.mean_speed_px_s,
                self.config.slow_speed_threshold_px_s,
            )
            events.append(
                self._event(
                    features,
                    timestamp_s,
                    event_type="Slow Walking",
                    score=score,
                    reason="Reduced movement speed detected.",
                )
            )

        if features.position_variance_px2 >= self.config.unstable_variance_threshold_px2:
            score = _ratio(
                features.position_variance_px2,
                self.config.unstable_variance_threshold_px2,
            )
            events.append(
                self._event(
                    features,
                    timestamp_s,
                    event_type="Tracking Instability",
                    score=score,
                    reason="Unstable tracking movement detected.",
                )
            )

        return events

    def _event(
        self,
        features: BehaviorFeatures,
        timestamp_s: float,
        event_type: str,
        score: float,
        reason: str,
    ) -> BehaviorEvent:
        bounded_score = max(0.0, min(1.0, score))
        return BehaviorEvent(
            event_id=f"track-{features.track_id}:{event_type}:{timestamp_s:.3f}",
            track_id=features.track_id,
            event_type=event_type,
            severity=_severity(bounded_score),
            score=bounded_score,
            timestamp_s=timestamp_s,
            reason=reason,
            feature_snapshot=features.to_dict(),
        )


def _ratio(value: float, threshold: float) -> float:
    if threshold <= 0:
        return 1.0
    return min(1.0, value / threshold)


def _inverse_ratio(value: float, threshold: float) -> float:
    if threshold <= 0:
        return 1.0
    return 1.0 - min(1.0, value / threshold)


def _severity(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"
