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
            observation_confidence < self.config.min_event_confidence
            or features.observations < self.config.min_track_frames
        )
        fall_like_evidence = _fall_like_motion_evidence(
            features,
            observation=observation,
            frame_size=frame_size,
            config=self.config,
        )
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

        anomaly_threshold = self.config.unstable_variance_threshold_px2 * 1.25
        if features.position_variance_px2 >= anomaly_threshold:
            if fall_like_evidence["strong"]:
                score = max(_ratio(features.position_variance_px2, anomaly_threshold), 0.82)
                events.append(
                    self._event(
                        features,
                        timestamp_s,
                        event_type="Fall-like motion event",
                        score=score,
                        severity="high",
                        reason=(
                            "Strong fall-like posture transition detected after abrupt downward "
                            "motion; review required."
                        ),
                        confidence=observation_confidence,
                        display_priority=5,
                    )
                )
                return events

            if near_frame_boundary or low_visual_evidence:
                return events

            score = _ratio(
                features.position_variance_px2,
                anomaly_threshold,
            )
            events.append(
                self._event(
                    features,
                    timestamp_s,
                    event_type="Movement anomaly",
                    score=min(score, 0.65),
                    severity="review_needed",
                    reason="Movement pattern changed abruptly, but fall evidence is inconclusive.",
                    confidence=observation_confidence,
                    display_priority=35,
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


def _fall_like_motion_evidence(
    features: BehaviorFeatures,
    *,
    observation: TrackObservation | None,
    frame_size: tuple[int, int] | None,
    config: BehaviorConfig,
) -> dict[str, bool]:
    frame_height = frame_size[1] if frame_size is not None else 0
    center_y = observation.center[1] if observation is not None else 0.0
    remains_visible = bool(
        observation is not None
        and observation.confidence >= max(0.34, config.min_event_confidence - 0.16)
        and features.observations >= max(6, config.min_track_frames - 2)
    )
    abrupt_downward_center_motion = features.recent_vertical_delta_px >= 10.0
    abrupt_downward_velocity = features.vertical_speed_px_s >= 95.0
    posture_collapse = features.bbox_height_change_ratio >= 0.12
    width_expansion = features.bbox_width_change_ratio >= 0.08
    aspect_ratio_transition = features.bbox_aspect_ratio_change >= 0.08
    low_wide_posture = features.recent_aspect_ratio >= 0.46
    sudden_stop_after_drop = bool(
        features.mean_speed_px_s >= config.slow_speed_threshold_px_s * 3.2
        and features.recent_speed_px_s <= config.slow_speed_threshold_px_s * 1.4
    )
    strong_motion_window = (
        features.position_variance_px2 >= config.unstable_variance_threshold_px2 * 2.4
    )
    near_floor = bool(frame_height > 0 and center_y >= frame_height * 0.62)

    primary_motion = abrupt_downward_center_motion or abrupt_downward_velocity
    posture_transition = posture_collapse and (width_expansion or aspect_ratio_transition)
    support_signals = sum(
        (
            1 if low_wide_posture else 0,
            1 if sudden_stop_after_drop else 0,
            1 if strong_motion_window else 0,
            1 if near_floor else 0,
        )
    )
    return {
        "strong": bool(
            remains_visible
            and primary_motion
            and posture_transition
            and support_signals >= 2
        )
    }
