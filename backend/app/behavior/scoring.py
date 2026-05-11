"""Explainable heuristic event scoring."""

from __future__ import annotations

from app.behavior.events import BehaviorEvent
from app.behavior.features import BehaviorFeatures
from app.config import BehaviorConfig
from app.schemas.tracking import TrackObservation


class EventScorer:
    """Score behavior features against Phase 1 mobility thresholds."""

    def __init__(self, config: BehaviorConfig) -> None:
        self.config = config

    def score(
        self,
        features: BehaviorFeatures,
        timestamp_s: float,
        observation: TrackObservation | None = None,
        frame_size: tuple[int, int] | None = None,
    ) -> list[BehaviorEvent]:
        if not features.is_confirmed:
            return []
        if features.duration_s < self.config.min_track_duration_s:
            return []

        near_frame_boundary = _near_frame_boundary(observation, frame_size)
        observation_confidence = observation.confidence if observation is not None else 1.0
        low_visual_evidence = bool(
            observation_confidence < self.config.min_event_confidence * 0.8
            or features.observations < max(4, self.config.min_track_frames // 2)
        )
        strong_risk = _strong_mobility_risk(features, self.config)
        events: list[BehaviorEvent] = []
        if features.dwell_time_s >= self.config.dwell_time_threshold_s * 1.5:
            score = _ratio(features.dwell_time_s, self.config.dwell_time_threshold_s)
            events.append(
                self._event(
                    features,
                    timestamp_s,
                    event_type="Movement anomaly",
                    score=min(0.65, score),
                    severity="review_needed",
                    reason="Sustained low movement detected; review in context.",
                    confidence=observation_confidence,
                    display_priority=45,
                )
            )

        if (
            features.mean_speed_px_s <= self.config.slow_speed_threshold_px_s
            and features.duration_s >= self.config.min_track_duration_s * 2
            and not low_visual_evidence
        ):
            score = _inverse_ratio(
                features.mean_speed_px_s,
                self.config.slow_speed_threshold_px_s,
            )
            events.append(
                self._event(
                    features,
                    timestamp_s,
                    event_type="Slow walking",
                    score=score,
                    severity="normal",
                    reason="Slow, consistent walking pattern observed.",
                    confidence=observation_confidence,
                    display_priority=80,
                )
            )

        strong_risk_threshold = self.config.unstable_variance_threshold_px2 * 1.25
        review_threshold = self.config.unstable_variance_threshold_px2 * 2.8
        should_emit_high = strong_risk and features.position_variance_px2 >= strong_risk_threshold
        should_emit_review = features.position_variance_px2 >= review_threshold

        if _postural_transition(features, self.config) and not _fall_like_motion(features, self.config):
            events.append(
                self._event(
                    features,
                    timestamp_s,
                    event_type="Postural Transition",
                    score=0.55,
                    severity="medium",
                    reason="Controlled postural change detected; subject appears to be transitioning between positions.",
                    confidence=observation_confidence,
                    display_priority=30,
                )
            )

        if should_emit_high or should_emit_review:
            score = _ratio(
                features.position_variance_px2,
                strong_risk_threshold if should_emit_high else review_threshold,
            )
            if should_emit_high:
                score = max(score, 0.8)
                event_type = (
                    "Fall-like motion event"
                    if _fall_like_motion(features, self.config)
                    else "Abrupt trajectory change"
                )
                severity = "high"
                reason = "Strong fall-like or abrupt motion evidence detected; requires review."
                display_priority = 10
            else:
                score = min(score, 0.65)
                event_type = "Abrupt trajectory change"
                severity = "review_needed"
                reason = "Trajectory irregularity detected; review needed."
                display_priority = 35
                if near_frame_boundary or low_visual_evidence:
                    score = min(score, 0.55)
                    reason = (
                        "Trajectory irregularity detected near frame boundary or with"
                        " weaker visual evidence; review needed."
                    )
            events.append(
                self._event(
                    features,
                    timestamp_s,
                    event_type=event_type,
                    score=score,
                    severity=severity,
                    reason=reason,
                    confidence=observation_confidence,
                    display_priority=display_priority,
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
        severity: str | None = None,
        confidence: float = 0.0,
        display_priority: int = 50,
    ) -> BehaviorEvent:
        bounded_score = max(0.0, min(1.0, score))
        return BehaviorEvent(
            event_id=f"track-{features.track_id}:{event_type}:{timestamp_s:.3f}",
            track_id=features.track_id,
            event_type=event_type,
            severity=severity or _severity(bounded_score),
            score=bounded_score,
            timestamp_s=timestamp_s,
            reason=reason,
            feature_snapshot=features.to_dict(),
            confidence=confidence,
            display_priority=display_priority,
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
        return "review_needed"
    return "normal"


def _near_frame_boundary(
    observation: TrackObservation | None,
    frame_size: tuple[int, int] | None,
) -> bool:
    if observation is None or frame_size is None:
        return False
    frame_width, frame_height = frame_size
    if frame_width <= 0 or frame_height <= 0:
        return False
    margin_x = max(12.0, frame_width * 0.04)
    margin_y = max(12.0, frame_height * 0.04)
    x1, y1, x2, y2 = observation.bbox.to_xyxy()
    return bool(
        x1 <= margin_x
        or y1 <= margin_y
        or x2 >= frame_width - margin_x
        or y2 >= frame_height - margin_y
    )


def _strong_mobility_risk(features: BehaviorFeatures, config: BehaviorConfig) -> bool:
    abrupt_vertical_shift = features.recent_vertical_delta_px >= 28.0
    abrupt_scale_change = features.bbox_height_change_ratio >= 0.28
    sudden_stop_after_motion = bool(
        features.mean_speed_px_s >= config.slow_speed_threshold_px_s * 2.2
        and features.recent_speed_px_s <= config.slow_speed_threshold_px_s * 0.45
    )
    repeated_direction_changes = bool(
        features.direction_changes >= 6
        and features.bbox_height_change_ratio >= 0.02
        and features.position_variance_px2 >= config.unstable_variance_threshold_px2 * 1.6
    )
    # Posture collapse: bbox went from standing-portrait to near-horizontal.
    abrupt_posture_collapse = _posture_collapse(features, config)
    return bool(
        (abrupt_vertical_shift and abrupt_scale_change)
        or sudden_stop_after_motion
        or repeated_direction_changes
        or abrupt_posture_collapse
    )


def _fall_like_motion(features: BehaviorFeatures, config: BehaviorConfig) -> bool:
    motion_based = bool(
        features.recent_vertical_delta_px >= 28.0
        and features.bbox_height_change_ratio >= 0.28
        and features.position_variance_px2 >= config.unstable_variance_threshold_px2 * 1.25
    )
    # Posture-based: subject went from upright (portrait bbox) to collapsed (square/landscape).
    posture_based = _posture_collapse(features, config)
    return motion_based or posture_based


def _posture_collapse(features: BehaviorFeatures, config: BehaviorConfig) -> bool:
    """True when the bbox has shifted from a standing-portrait shape to near-horizontal."""
    if features.bbox_aspect_ratio <= 0.0 or features.baseline_aspect_ratio <= 0.0:
        return False
    drop = features.baseline_aspect_ratio - features.bbox_aspect_ratio
    return bool(
        features.bbox_aspect_ratio < 1.2          # currently nearly square or landscape
        and features.baseline_aspect_ratio >= 1.6  # was clearly standing upright
        and drop >= 0.6                            # dropped significantly from baseline
        and features.position_variance_px2 >= config.unstable_variance_threshold_px2 * 0.25
    )


def _postural_transition(features: BehaviorFeatures, config: BehaviorConfig) -> bool:
    """Detect controlled deceleration from walking to a near-stop (sit/stand assist)."""
    return bool(
        features.mean_speed_px_s >= config.slow_speed_threshold_px_s * 1.4
        and features.recent_speed_px_s <= config.slow_speed_threshold_px_s * 0.55
        and features.position_variance_px2 >= config.unstable_variance_threshold_px2 * 0.3
    )
