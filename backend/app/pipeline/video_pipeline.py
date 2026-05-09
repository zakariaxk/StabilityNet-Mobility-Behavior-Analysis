"""High-level video analysis pipeline orchestration."""

from __future__ import annotations

import logging
import math
import time
from datetime import UTC, datetime

from app.behavior.events import BehaviorEvent
from app.behavior.features import BehaviorFeatures, extract_features
from app.behavior.scoring import EventScorer
from app.behavior.track_state import TrackStore
from app.config import AnalysisRequest
from app.pipeline.annotated_video import AnnotatedVideoWriter
from app.pipeline.frame_reader import VideoFrameReader, VideoOpenError
from app.pipeline.result_writer import write_json
from app.schemas.detection import BoundingBox
from app.schemas.tracking import TrackObservation
from app.vision.detector import DetectorInferenceError
from app.vision.sort_tracker import SortTracker
from app.vision.yolo_detector import YOLOPersonDetector

logger = logging.getLogger(__name__)


class AnalysisPipelineError(RuntimeError):
    """Raised when analysis fails inside the per-frame pipeline."""


def analyze_video(request: AnalysisRequest) -> dict[str, object]:
    """Probe a video and write a Phase 1B analysis payload.

    Detection, tracking, and behavior scoring are added in later Phase 1 steps.
    This keeps the CLI useful while the pipeline is assembled incrementally.
    """

    started_at = time.perf_counter()
    logger.info("analysis started", extra={"video_path": str(request.video_path)})
    reader = VideoFrameReader(
        request.video_path,
        fallback_fps=request.config.fallback_fps,
    )
    metadata = reader.metadata()
    detector = YOLOPersonDetector(request.config.detector)
    tracker = SortTracker(request.config.tracker)
    track_store = TrackStore()
    scorer = EventScorer(request.config.behavior)
    analysis_frame_stride = _effective_analysis_stride(
        source_fps=metadata.fps,
        configured_stride=request.config.analysis_frame_stride,
        target_fps=request.config.analysis_target_fps,
    )
    analysis_stride_mode = (
        "configured" if request.config.analysis_frame_stride > 0 else "auto"
    )

    frames_processed = 0
    analyzed_frames_count = 0
    frame_summaries: list[dict[str, object]] = []
    all_observations: list[TrackObservation] = []
    latest_features: dict[int, BehaviorFeatures] = {}
    events: list[BehaviorEvent] = []
    last_event_timestamps: dict[tuple[int, str], float] = {}
    timing_seconds: dict[str, float] = {
        "decode": 0.0,
        "inference": 0.0,
        "tracking": 0.0,
        "event": 0.0,
        "annotation": 0.0,
        "encode": 0.0,
    }
    previous_analysis_observations: dict[int, TrackObservation] = {}
    frame_loop_started_at = time.perf_counter()

    with AnnotatedVideoWriter(
        request.annotated_video_path,
        fps=metadata.fps,
        fallback_fps=request.config.fallback_fps,
        behavior_config=request.config.behavior,
        max_rendered_labels=request.config.max_rendered_labels_per_frame,
        output_max_width=request.config.annotated_output_max_width,
    ) as annotated_writer:
        frame_iterator = reader.frames(max_frames=request.config.max_frames)
        while True:
            decode_started_at = time.perf_counter()
            try:
                frame = next(frame_iterator)
            except StopIteration:
                break
            timing_seconds["decode"] += time.perf_counter() - decode_started_at

            should_run_analysis = frame.index % analysis_frame_stride == 0
            detections: list = []
            analysis_observations: list[TrackObservation] = []
            overlay_observations: list[TrackObservation] = []
            frame_features_by_track: dict[int, BehaviorFeatures] = {}
            frame_events: list[BehaviorEvent] = []

            def add_event(event: BehaviorEvent) -> None:
                event_key = (event.track_id, event.event_type)
                previous_timestamp = last_event_timestamps.get(event_key)
                if (
                    previous_timestamp is not None
                    and event.timestamp_s - previous_timestamp
                    < request.config.behavior.event_cooldown_s
                ):
                    return
                last_event_timestamps[event_key] = event.timestamp_s
                events.append(event)
                frame_events.append(event)

            try:
                if should_run_analysis:
                    inference_started_at = time.perf_counter()
                    detections = detector.detect(frame.image)
                    timing_seconds["inference"] += time.perf_counter() - inference_started_at

                    tracking_started_at = time.perf_counter()
                    analysis_observations = tracker.update(
                        detections,
                        frame.index,
                        frame.timestamp_s,
                    )
                    timing_seconds["tracking"] += time.perf_counter() - tracking_started_at
                    analyzed_frames_count += 1
                    all_observations.extend(analysis_observations)

                    for event in _track_end_events(
                        previous_observations=previous_analysis_observations,
                        current_observations=analysis_observations,
                        latest_features=latest_features,
                        frame_width=metadata.width,
                        frame_height=metadata.height,
                        timestamp_s=frame.timestamp_s,
                    ):
                        add_event(event)

                    camera_motion_event = _camera_motion_uncertainty_event(
                        previous_observations=previous_analysis_observations,
                        current_observations=analysis_observations,
                        frame_width=metadata.width,
                        frame_height=metadata.height,
                        timestamp_s=frame.timestamp_s,
                    )
                    if camera_motion_event is not None:
                        add_event(camera_motion_event)

                    event_started_at = time.perf_counter()
                    for observation in analysis_observations:
                        history = track_store.update(observation)
                        features = extract_features(history, request.config.behavior)
                        latest_features[features.track_id] = features
                        frame_features_by_track[features.track_id] = features

                        uncertainty_event = _insufficient_evidence_event(
                            observation=observation,
                            features=features,
                            timestamp_s=frame.timestamp_s,
                        )
                        if uncertainty_event is not None:
                            add_event(uncertainty_event)

                        for event in scorer.score(
                            features,
                            observation.timestamp_s,
                            observation=observation,
                            frame_size=(metadata.width, metadata.height),
                        ):
                            add_event(event)
                    timing_seconds["event"] += time.perf_counter() - event_started_at

                    previous_analysis_observations = {
                        observation.track_id: observation for observation in analysis_observations
                    }
                    overlay_observations = [
                        _overlay_observation(
                            observation=observation,
                            frame_index=frame.index,
                            timestamp_s=frame.timestamp_s,
                            confidence_scale=1.0,
                        )
                        for observation in analysis_observations
                    ]
                else:
                    overlay_observations = [
                        _overlay_observation(
                            observation=observation,
                            frame_index=frame.index,
                            timestamp_s=frame.timestamp_s,
                            confidence_scale=0.96,
                        )
                        for observation in previous_analysis_observations.values()
                    ]
                    frame_features_by_track = {
                        track_id: features
                        for track_id, features in latest_features.items()
                        if track_id in {observation.track_id for observation in overlay_observations}
                    }
            except DetectorInferenceError:
                raise
            except Exception as exc:
                raise AnalysisPipelineError(
                    f"Analysis failed while processing frame {frame.index}."
                ) from exc

            annotation_started_at = time.perf_counter()
            annotated_writer.write(
                frame=frame.image,
                detections=detections,
                observations=overlay_observations,
                frame_features=frame_features_by_track,
                events=frame_events,
                total_events_count=len(events),
                frame_index=frame.index,
                timestamp_s=frame.timestamp_s,
                hud_source_fps=metadata.fps,
                hud_processing_fps=_running_fps(frame_loop_started_at, frames_processed + 1),
                hud_scene_reliability=None,
            )
            timing_seconds["annotation"] += time.perf_counter() - annotation_started_at

            frame_summaries.append(
                {
                    "frame_index": frame.index,
                    "timestamp_s": frame.timestamp_s,
                    "detections": [detection.to_dict() for detection in detections],
                    "tracks": [observation.to_dict() for observation in analysis_observations],
                    "features": [features.to_dict() for features in frame_features_by_track.values()],
                    "events": [event.to_dict() for event in frame_events],
                    "analysis_sampled": should_run_analysis,
                }
            )
            frames_processed += 1
        frame_loop_seconds = time.perf_counter() - frame_loop_started_at
    timing_seconds["encode"] = annotated_writer.transcode_seconds

    if frames_processed == 0:
        raise VideoOpenError("Video file contains no readable frames.")

    tracks = _summarize_tracks(
        all_observations,
        latest_features,
        frame_width=metadata.width,
        frame_height=metadata.height,
        config=request.config.behavior,
    )
    raw_track_count = len(tracks)
    qualified_tracks = [track for track in tracks if track.get("qualified") is True]
    scene_reliability = _scene_reliability(
        tracks=tracks,
        raw_events=events,
        frames_processed=frames_processed,
    )
    display_events, suppressed_event_count = _display_events(
        events=events,
        tracks=tracks,
        scene_reliability=scene_reliability,
    )
    event_payloads = [event.to_dict() for event in display_events]
    raw_event_count = len(events)
    end_to_end_seconds = time.perf_counter() - started_at
    analysis_throughput_fps = (
        frames_processed / frame_loop_seconds
        if frames_processed > 0 and frame_loop_seconds > 0
        else None
    )
    analysis_inference_throughput_fps = (
        analyzed_frames_count / frame_loop_seconds
        if analyzed_frames_count > 0 and frame_loop_seconds > 0
        else None
    )
    sampled_analysis_fps = (
        analyzed_frames_count / (frames_processed / metadata.fps)
        if analyzed_frames_count > 0 and frames_processed > 0 and metadata.fps > 0
        else None
    )
    effective_analysis_fps = (
        metadata.fps / analysis_frame_stride if metadata.fps > 0 else None
    )
    end_to_end_throughput_fps = (
        frames_processed / end_to_end_seconds
        if frames_processed > 0 and end_to_end_seconds > 0
        else None
    )
    annotated_video_url = (
        request.annotated_video_url
        if request.annotated_video_path is not None and request.annotated_video_path.exists()
        else None
    )
    timing_seconds["total"] = end_to_end_seconds
    timing_ms = {
        f"{name}_time_ms": seconds * 1000.0
        for name, seconds in timing_seconds.items()
    }

    result: dict[str, object] = {
        "status": "completed",
        "analysis_version": "phase-1g",
        "created_at": datetime.now(UTC).isoformat(),
        "video": metadata.to_dict(),
        "frames_processed": frames_processed,
        "frames_analyzed": analyzed_frames_count,
        "analyzed_frames_count": analyzed_frames_count,
        "analysis_frame_stride": analysis_frame_stride,
        "analysis_stride_mode": analysis_stride_mode,
        "analysis_target_fps": request.config.analysis_target_fps,
        "analysis_resolution_width": request.config.detector.analysis_width,
        "annotated_output_max_width": request.config.annotated_output_max_width,
        "raw_track_count": raw_track_count,
        "qualified_subject_count": len(qualified_tracks),
        "tracks_count": len(qualified_tracks),
        "confirmed_tracks_count": sum(1 for track in tracks if track.get("is_confirmed") is True),
        "raw_event_count": raw_event_count,
        "events_suppressed_count": suppressed_event_count,
        "mobility_event_count": len(event_payloads),
        "events_count": len(event_payloads),
        "fps": metadata.fps,
        "source_fps": metadata.fps,
        "source_video_fps": metadata.fps,
        # Annotated output is written at source FPS for faithful playback timing.
        "playback_fps": metadata.fps,
        # This is CPU throughput for the per-frame analysis loop (detection/tracking/scoring).
        "cpu_analysis_throughput_fps": analysis_throughput_fps,
        "analysis_throughput_fps": analysis_throughput_fps,
        # Throughput of sampled inference frames only (useful when frame stride > 1).
        "analysis_inference_throughput_fps": analysis_inference_throughput_fps,
        # Effective sampled analysis cadence in source-video FPS terms.
        "effective_analysis_fps": effective_analysis_fps,
        "sampled_analysis_fps": sampled_analysis_fps,
        # This includes extra overhead outside the frame loop (setup + output writing).
        "end_to_end_processing_fps": end_to_end_throughput_fps,
        "end_to_end_throughput_fps": end_to_end_throughput_fps,
        # Keep processing_fps as a backwards-compatible alias of end-to-end
        # throughput so clients do not overstate model inference speed.
        "processing_fps": end_to_end_throughput_fps,
        "frame_loop_seconds": frame_loop_seconds,
        "end_to_end_seconds": end_to_end_seconds,
        "timing_seconds": timing_seconds,
        "timing_ms": timing_ms,
        "processing_profile": {
            **timing_ms,
            "frames_processed": frames_processed,
            "frames_analyzed": analyzed_frames_count,
            "source_fps": metadata.fps,
            "cpu_analysis_throughput_fps": analysis_throughput_fps,
            "end_to_end_processing_fps": end_to_end_throughput_fps,
            "effective_analysis_fps": effective_analysis_fps,
        },
        "scene_reliability": scene_reliability["category"],
        "scene_reliability_score": scene_reliability["score"],
        "scene_reliability_reasons": scene_reliability["reasons"],
        "annotated_video_url": annotated_video_url,
        "message": None,
        "frames": frame_summaries,
        "tracks": tracks,
        "qualified_tracks": qualified_tracks,
        "events": event_payloads,
        "debug": {
            "raw_track_count": raw_track_count,
            "raw_event_count": raw_event_count,
            "qualified_subject_count": len(qualified_tracks),
            "analysis_frame_stride": analysis_frame_stride,
            "analysis_stride_mode": analysis_stride_mode,
            "analysis_resolution_width": request.config.detector.analysis_width,
            "annotated_output_max_width": request.config.annotated_output_max_width,
        },
    }
    write_json(request.output_path, result)
    logger.info(
        "analysis completed",
        extra={
            "video_path": str(request.video_path),
            "frames_processed": frames_processed,
            "raw_track_count": raw_track_count,
            "qualified_subject_count": len(qualified_tracks),
            "events_count": len(event_payloads),
        },
    )
    return result


def _summarize_tracks(
    observations: list[TrackObservation],
    features_by_track: dict[int, BehaviorFeatures],
    *,
    frame_width: int,
    frame_height: int,
    config: object,
) -> list[dict[str, object]]:
    summaries: dict[int, dict[str, object]] = {}
    confidence_totals: dict[int, float] = {}
    boundary_counts: dict[int, int] = {}
    trajectories: dict[int, list[dict[str, float | int]]] = {}
    for observation in observations:
        summary = summaries.setdefault(
            observation.track_id,
            {
                "id": observation.track_id,
                "track_id": observation.track_id,
                "frames": 0,
                "observations": 0,
                "first_timestamp_s": observation.timestamp_s,
                "last_timestamp_s": observation.timestamp_s,
                "duration_seconds": 0.0,
                "avg_confidence": None,
                "trajectory": [],
                "is_confirmed": False,
                "qualified": False,
                "eligible": False,
                "suppression_reason": None,
            },
        )
        summary["observations"] = int(summary["observations"]) + 1
        summary["frames"] = int(summary["frames"]) + 1
        summary["last_timestamp_s"] = observation.timestamp_s
        summary["is_confirmed"] = bool(summary["is_confirmed"]) or observation.is_confirmed
        confidence_totals[observation.track_id] = (
            confidence_totals.get(observation.track_id, 0.0) + observation.confidence
        )
        if _bbox_near_boundary(observation.bbox, frame_width, frame_height):
            boundary_counts[observation.track_id] = boundary_counts.get(observation.track_id, 0) + 1
        center_x, center_y = observation.center
        trajectories.setdefault(observation.track_id, []).append(
            {
                "x": center_x,
                "y": center_y,
                "timestamp_s": observation.timestamp_s,
                "frame_index": observation.frame_index,
                "confidence": observation.confidence,
            }
        )

    for track_id, features in features_by_track.items():
        summaries.setdefault(
            track_id,
            {
                "id": track_id,
                "track_id": track_id,
                "frames": features.observations,
                "observations": features.observations,
                "first_timestamp_s": 0.0,
                "last_timestamp_s": 0.0,
                "duration_seconds": features.duration_s,
                "avg_confidence": None,
                "trajectory": trajectories.get(track_id, []),
                "is_confirmed": features.is_confirmed,
                "qualified": False,
                "eligible": False,
                "suppression_reason": None,
            },
        )
        summaries[track_id]["features"] = features.to_dict()
        summaries[track_id]["duration_seconds"] = features.duration_s

    for track_id, summary in summaries.items():
        observations_count = int(summary.get("observations", 0) or 0)
        first_timestamp = float(summary.get("first_timestamp_s", 0.0) or 0.0)
        last_timestamp = float(summary.get("last_timestamp_s", first_timestamp) or first_timestamp)
        summary["duration_seconds"] = max(0.0, last_timestamp - first_timestamp)
        summary["trajectory"] = trajectories.get(track_id, [])
        if observations_count > 0:
            summary["avg_confidence"] = confidence_totals.get(track_id, 0.0) / observations_count
        _apply_track_qualification(
            summary,
            boundary_observations=boundary_counts.get(track_id, 0),
            config=config,
        )

    return list(summaries.values())


def _effective_analysis_stride(
    *,
    source_fps: float,
    configured_stride: int,
    target_fps: float,
) -> int:
    if configured_stride > 0:
        return max(1, configured_stride)
    if not math.isfinite(source_fps) or source_fps <= 0:
        return 1
    if not math.isfinite(target_fps) or target_fps <= 0:
        return 1
    if source_fps <= target_fps * 1.5:
        return 1
    return max(1, int(math.ceil(source_fps / target_fps)))


def _apply_track_qualification(
    summary: dict[str, object],
    *,
    boundary_observations: int,
    config: object,
) -> None:
    observations_count = int(summary.get("observations", 0) or 0)
    duration_s = float(summary.get("duration_seconds", 0.0) or 0.0)
    avg_confidence = summary.get("avg_confidence")
    confidence = float(avg_confidence) if isinstance(avg_confidence, (int, float)) else 0.0
    is_confirmed = summary.get("is_confirmed") is True
    boundary_ratio = boundary_observations / observations_count if observations_count > 0 else 1.0
    min_duration_s = float(getattr(config, "min_track_duration_s", 1.0))
    min_frames = int(getattr(config, "min_track_frames", 10))
    min_confidence = float(getattr(config, "min_event_confidence", 0.5))

    suppression_reasons: list[str] = []
    if not is_confirmed:
        suppression_reasons.append("unconfirmed")
    if duration_s < min_duration_s:
        suppression_reasons.append("track_too_short")
    if observations_count < min_frames:
        suppression_reasons.append("too_few_observations")
    if confidence < min_confidence:
        suppression_reasons.append("low_confidence")
    boundary_uncertain = boundary_ratio >= 0.85
    if boundary_uncertain and duration_s < min_duration_s * 2.0:
        suppression_reasons.append("mostly_near_frame_boundary")

    features = summary.get("features")
    feature_record = features if isinstance(features, dict) else {}
    motion_state = _track_motion_state(feature_record)
    summary["raw_id"] = summary.get("track_id")
    summary["frame_count"] = observations_count
    summary["confidence"] = confidence
    summary["boundary_observation_ratio"] = boundary_ratio
    summary["motion_state"] = "review" if boundary_uncertain and not suppression_reasons else motion_state
    if suppression_reasons:
        summary["status"] = "Insufficient Evidence"
        summary["risk_level"] = "unknown"
    elif boundary_uncertain:
        summary["status"] = "Review Needed"
        summary["risk_level"] = "review"
    else:
        summary["status"] = "Stable"
        summary["risk_level"] = "normal"
    summary["qualified"] = not suppression_reasons
    summary["eligible"] = not suppression_reasons
    summary["suppression_reason"] = ", ".join(suppression_reasons) or None


def _track_motion_state(feature_record: dict[str, object]) -> str:
    variance = _float_value(feature_record.get("position_variance_px2"))
    if variance is not None and variance >= 1125.0:
        return "review"
    dwell_time = _float_value(feature_record.get("dwell_time_s"))
    if dwell_time is not None and dwell_time >= 8.0:
        return "stationary"
    recent_speed = _float_value(feature_record.get("recent_speed_px_s"))
    mean_speed = _float_value(feature_record.get("mean_speed_px_s"))
    speed = recent_speed if recent_speed is not None else mean_speed
    if speed is not None and speed <= 18.0:
        return "slow walking"
    return "walking"


def _scene_reliability(
    *,
    tracks: list[dict[str, object]],
    raw_events: list[BehaviorEvent],
    frames_processed: int,
) -> dict[str, object]:
    raw_track_count = len(tracks)
    qualified_count = sum(1 for track in tracks if track.get("qualified") is True)
    short_or_suppressed_count = raw_track_count - qualified_count
    short_track_rate = short_or_suppressed_count / raw_track_count if raw_track_count else 0.0
    camera_motion_count = sum(
        1 for event in raw_events if event.event_type == "Camera motion uncertainty"
    )
    reasons: list[str] = []
    score = 1.0

    if raw_track_count >= 20:
        score -= 0.28
        reasons.append("crowded scene")
    elif raw_track_count >= 10:
        score -= 0.14
        reasons.append("multiple simultaneous subjects")

    if raw_track_count >= 4 and short_track_rate >= 0.45:
        score -= 0.32
        reasons.append("high track fragmentation")
    elif raw_track_count >= 4 and short_track_rate >= 0.25:
        score -= 0.18
        reasons.append("some track fragmentation")

    if camera_motion_count > 0:
        score -= 0.25
        reasons.append("camera motion uncertainty")

    if frames_processed > 0 and raw_track_count / frames_processed > 0.045:
        score -= 0.12
        reasons.append("dense detections over time")

    if len(raw_events) >= 35:
        score -= 0.22
        reasons.append("many uncertain events")

    bounded_score = max(0.0, min(1.0, score))
    if bounded_score < 0.48:
        category = "Low"
    elif bounded_score < 0.72:
        category = "Medium"
    else:
        category = "High"

    return {
        "category": category,
        "score": round(bounded_score, 3),
        "reasons": reasons or ["stable camera and low fragmentation"],
    }


def _display_events(
    *,
    events: list[BehaviorEvent],
    tracks: list[dict[str, object]],
    scene_reliability: dict[str, object],
) -> tuple[list[BehaviorEvent], int]:
    tracks_by_id = {
        int(track["track_id"]): track
        for track in tracks
        if isinstance(track.get("track_id"), int)
    }
    reliability_category = str(scene_reliability.get("category", "High"))
    display_events: list[BehaviorEvent] = []
    suppressed = 0

    for event in events:
        track = tracks_by_id.get(event.track_id)
        if event.track_id > 0 and track is not None and track.get("qualified") is not True:
            if event.event_type not in {
                "Insufficient visual evidence",
                "Subject leaving frame",
            }:
                suppressed += 1
                continue

        normalized_event = _normalize_display_event(
            event,
            track=track,
            reliability_category=reliability_category,
        )
        display_events.append(normalized_event)

    merged_events = _merge_nearby_events(display_events)
    merged_events.sort(
        key=lambda event: (
            event.display_priority,
            event.timestamp_s,
            event.track_id,
        )
    )
    return merged_events, suppressed + (len(display_events) - len(merged_events))


def _normalize_display_event(
    event: BehaviorEvent,
    *,
    track: dict[str, object] | None,
    reliability_category: str,
) -> BehaviorEvent:
    event_type = _event_type_label(event.event_type)
    severity = _event_severity(event_type, event.severity)
    reason = event.reason
    if (
        reliability_category == "Low"
        and severity == "high"
        and event_type != "Fall-like motion event"
    ):
        severity = "review_needed"
        reason = f"{reason} Scene reliability is low, so this is marked for review."
    if event_type == "Insufficient visual evidence":
        severity = "insufficient_evidence"
    confidence = event.confidence
    if confidence <= 0.0 and track is not None:
        confidence = float(track.get("avg_confidence") or track.get("confidence") or 0.0)
    return BehaviorEvent(
        event_id=event.event_id,
        track_id=event.track_id,
        event_type=event_type,
        severity=severity,
        score=event.score,
        timestamp_s=event.timestamp_s,
        reason=reason,
        feature_snapshot=event.feature_snapshot,
        confidence=confidence,
        display_priority=_event_priority(event_type, severity),
        merged_count=event.merged_count,
    )


def _event_type_label(event_type: str) -> str:
    labels = {
        "Prolonged Stop": "Movement anomaly",
        "Tracking Instability": "Movement anomaly",
        "Abrupt trajectory change": "Movement anomaly",
        "Subject leaving frame": "Track ended near boundary",
        "Slow Walking": "Slow walking",
    }
    return labels.get(event_type, event_type)


def _event_severity(event_type: str, severity: str) -> str:
    normalized = severity.lower()
    if event_type in {"Insufficient visual evidence", "Track ended near boundary"}:
        return "insufficient_evidence"
    if normalized in {"high", "review_needed", "normal", "insufficient_evidence"}:
        return normalized
    if normalized in {"medium", "uncertain"}:
        return "review_needed"
    if normalized == "low":
        return "normal"
    return "review_needed"


def _event_priority(event_type: str, severity: str) -> int:
    if event_type == "Fall-like motion event":
        return 5
    if severity == "high":
        return 10
    if event_type == "Movement anomaly":
        return 25
    if event_type == "Camera motion uncertainty":
        return 35
    if severity == "review_needed":
        return 45
    if severity == "insufficient_evidence":
        return 65
    return 85


def _merge_nearby_events(events: list[BehaviorEvent]) -> list[BehaviorEvent]:
    merged: list[BehaviorEvent] = []
    for event in sorted(events, key=lambda item: (item.track_id, item.event_type, item.timestamp_s)):
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous.track_id == event.track_id
            and previous.event_type == event.event_type
            and event.timestamp_s - previous.timestamp_s <= 2.5
        ):
            merged[-1] = BehaviorEvent(
                event_id=previous.event_id,
                track_id=previous.track_id,
                event_type=previous.event_type,
                severity=previous.severity,
                score=max(previous.score, event.score),
                timestamp_s=previous.timestamp_s,
                reason=previous.reason,
                feature_snapshot=previous.feature_snapshot,
                confidence=max(previous.confidence, event.confidence),
                display_priority=min(previous.display_priority, event.display_priority),
                merged_count=previous.merged_count + event.merged_count,
            )
            continue
        merged.append(event)
    return merged


def _float_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _running_fps(loop_started_at: float, frames_count: int) -> float | None:
    elapsed = time.perf_counter() - loop_started_at
    if elapsed <= 0 or frames_count <= 0:
        return None
    return frames_count / elapsed


def _overlay_observation(
    observation: TrackObservation,
    frame_index: int,
    timestamp_s: float,
    confidence_scale: float,
) -> TrackObservation:
    return TrackObservation(
        track_id=observation.track_id,
        bbox=observation.bbox,
        confidence=max(0.0, min(1.0, observation.confidence * confidence_scale)),
        frame_index=frame_index,
        timestamp_s=timestamp_s,
        is_confirmed=observation.is_confirmed,
    )


def _track_end_events(
    *,
    previous_observations: dict[int, TrackObservation],
    current_observations: list[TrackObservation],
    latest_features: dict[int, BehaviorFeatures],
    frame_width: int,
    frame_height: int,
    timestamp_s: float,
) -> list[BehaviorEvent]:
    current_track_ids = {observation.track_id for observation in current_observations}
    frame_events: list[BehaviorEvent] = []
    for track_id, previous_observation in previous_observations.items():
        if track_id in current_track_ids:
            continue

        if _bbox_near_boundary(previous_observation.bbox, frame_width, frame_height):
            frame_events.append(
                _custom_event(
                    track_id=track_id,
                    event_type="Subject leaving frame",
                    severity="review_needed",
                    timestamp_s=timestamp_s,
                    reason="Track ended near frame boundary; mobility estimate uncertain.",
                    feature_snapshot={"track_id": track_id},
                )
            )
            continue

        features = latest_features.get(track_id)
        observations = features.observations if features is not None else 0
        if previous_observation.confidence < 0.55 or observations < 8:
            frame_events.append(
                _custom_event(
                    track_id=track_id,
                    event_type="Insufficient visual evidence",
                    severity="insufficient_evidence",
                    timestamp_s=timestamp_s,
                    reason="Track ended without enough visual evidence for a strong conclusion.",
                    feature_snapshot={"track_id": track_id, "observations": observations},
                )
            )
    return frame_events


def _camera_motion_uncertainty_event(
    *,
    previous_observations: dict[int, TrackObservation],
    current_observations: list[TrackObservation],
    frame_width: int,
    frame_height: int,
    timestamp_s: float,
) -> BehaviorEvent | None:
    current_by_track = {observation.track_id: observation for observation in current_observations}
    shared_track_ids = sorted(set(previous_observations) & set(current_by_track))
    if len(shared_track_ids) < 2:
        return None

    vectors: list[tuple[float, float]] = []
    magnitudes: list[float] = []
    for track_id in shared_track_ids:
        previous_center = previous_observations[track_id].center
        current_center = current_by_track[track_id].center
        dx = current_center[0] - previous_center[0]
        dy = current_center[1] - previous_center[1]
        magnitude = (dx * dx + dy * dy) ** 0.5
        vectors.append((dx, dy))
        magnitudes.append(magnitude)

    mean_magnitude = sum(magnitudes) / len(magnitudes)
    movement_threshold = max(8.0, min(frame_width, frame_height) * 0.008)
    if mean_magnitude < movement_threshold:
        return None

    mean_dx = sum(vector[0] for vector in vectors) / len(vectors)
    mean_dy = sum(vector[1] for vector in vectors) / len(vectors)
    mean_norm = (mean_dx * mean_dx + mean_dy * mean_dy) ** 0.5
    if mean_norm <= 1e-6:
        return None

    coherence_terms: list[float] = []
    for dx, dy in vectors:
        norm = (dx * dx + dy * dy) ** 0.5
        if norm <= 1e-6:
            continue
        coherence_terms.append((dx * mean_dx + dy * mean_dy) / (norm * mean_norm))
    if not coherence_terms:
        return None
    coherence = sum(coherence_terms) / len(coherence_terms)
    if coherence < 0.75:
        return None

    return _custom_event(
        track_id=-1,
        event_type="Camera motion uncertainty",
        severity="review_needed",
        timestamp_s=timestamp_s,
        reason="Global track shift suggests camera motion; mobility estimate uncertain.",
        feature_snapshot={
            "shared_tracks": len(shared_track_ids),
            "mean_shift_px": round(mean_magnitude, 3),
            "coherence": round(coherence, 3),
        },
    )


def _insufficient_evidence_event(
    *,
    observation: TrackObservation,
    features: BehaviorFeatures,
    timestamp_s: float,
) -> BehaviorEvent | None:
    if observation.confidence >= 0.42 and features.observations >= 5:
        return None
    return _custom_event(
        track_id=observation.track_id,
        event_type="Insufficient visual evidence",
        severity="insufficient_evidence",
        timestamp_s=timestamp_s,
        reason="Low-confidence or fragmented track; requires review.",
        feature_snapshot=features.to_dict(),
    )


def _custom_event(
    *,
    track_id: int,
    event_type: str,
    severity: str,
    timestamp_s: float,
    reason: str,
    feature_snapshot: dict[str, bool | float | int] | None = None,
) -> BehaviorEvent:
    return BehaviorEvent(
        event_id=f"track-{track_id}:{event_type}:{timestamp_s:.3f}",
        track_id=track_id,
        event_type=event_type,
        severity=severity,
        score=0.0,
        timestamp_s=timestamp_s,
        reason=reason,
        feature_snapshot=feature_snapshot or {},
        confidence=0.0,
        display_priority=_event_priority(_event_type_label(event_type), severity),
    )


def _bbox_near_boundary(bbox: BoundingBox, frame_width: int, frame_height: int) -> bool:
    if frame_width <= 0 or frame_height <= 0:
        return False
    margin_x = max(12.0, frame_width * 0.045)
    margin_y = max(12.0, frame_height * 0.045)
    x1, y1, x2, y2 = bbox.to_xyxy()
    return bool(
        x1 <= margin_x
        or y1 <= margin_y
        or x2 >= frame_width - margin_x
        or y2 >= frame_height - margin_y
    )
