"""High-level video analysis pipeline orchestration."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from app.behavior.events import BehaviorEvent
from app.behavior.features import BehaviorFeatures, extract_features
from app.behavior.scoring import EventScorer
from app.behavior.track_state import TrackStore
from app.config import AnalysisRequest
from app.pipeline.frame_reader import VideoFrameReader, VideoOpenError
from app.pipeline.result_writer import write_json
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

    frames_processed = 0
    frame_summaries: list[dict[str, object]] = []
    all_observations: list[TrackObservation] = []
    latest_features: dict[int, BehaviorFeatures] = {}
    events: list[BehaviorEvent] = []
    emitted_event_keys: set[tuple[int, str]] = set()
    for frame in reader.frames(max_frames=request.config.max_frames):
        try:
            detections = detector.detect(frame.image)
            observations = tracker.update(detections, frame.index, frame.timestamp_s)
        except DetectorInferenceError:
            raise
        except Exception as exc:
            raise AnalysisPipelineError(
                f"Analysis failed while processing frame {frame.index}."
            ) from exc
        all_observations.extend(observations)
        frame_features: list[BehaviorFeatures] = []
        frame_events: list[BehaviorEvent] = []
        for observation in observations:
            history = track_store.update(observation)
            features = extract_features(history, request.config.behavior)
            latest_features[features.track_id] = features
            frame_features.append(features)
            for event in scorer.score(features, observation.timestamp_s):
                event_key = (event.track_id, event.event_type)
                if event_key in emitted_event_keys:
                    continue
                emitted_event_keys.add(event_key)
                events.append(event)
                frame_events.append(event)
        frame_summaries.append(
            {
                "frame_index": frame.index,
                "timestamp_s": frame.timestamp_s,
                "detections": [detection.to_dict() for detection in detections],
                "tracks": [observation.to_dict() for observation in observations],
                "features": [features.to_dict() for features in frame_features],
                "events": [event.to_dict() for event in frame_events],
            }
        )
        frames_processed += 1

    if frames_processed == 0:
        raise VideoOpenError("Video file contains no readable frames.")

    tracks = _summarize_tracks(all_observations, latest_features)
    event_payloads = [event.to_dict() for event in events]
    processing_seconds = time.perf_counter() - started_at
    processing_fps = (
        frames_processed / processing_seconds
        if frames_processed > 0 and processing_seconds > 0
        else None
    )

    result: dict[str, object] = {
        "status": "completed",
        "analysis_version": "phase-1f",
        "created_at": datetime.now(UTC).isoformat(),
        "video": metadata.to_dict(),
        "frames_processed": frames_processed,
        "tracks_count": len(tracks),
        "events_count": len(event_payloads),
        "fps": metadata.fps,
        "processing_fps": processing_fps,
        "annotated_video_url": request.annotated_video_url,
        "message": None,
        "frames": frame_summaries,
        "tracks": tracks,
        "events": event_payloads,
    }
    write_json(request.output_path, result)
    logger.info(
        "analysis completed",
        extra={
            "video_path": str(request.video_path),
            "frames_processed": frames_processed,
            "tracks_count": len(tracks),
            "events_count": len(event_payloads),
        },
    )
    return result


def _summarize_tracks(
    observations: list[TrackObservation],
    features_by_track: dict[int, BehaviorFeatures],
) -> list[dict[str, object]]:
    summaries: dict[int, dict[str, object]] = {}
    confidence_totals: dict[int, float] = {}
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
            },
        )
        summary["observations"] = int(summary["observations"]) + 1
        summary["frames"] = int(summary["frames"]) + 1
        summary["last_timestamp_s"] = observation.timestamp_s
        summary["is_confirmed"] = bool(summary["is_confirmed"]) or observation.is_confirmed
        confidence_totals[observation.track_id] = (
            confidence_totals.get(observation.track_id, 0.0) + observation.confidence
        )
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

    return list(summaries.values())
