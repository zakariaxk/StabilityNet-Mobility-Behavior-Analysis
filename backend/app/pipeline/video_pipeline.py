"""High-level video analysis pipeline orchestration."""

from __future__ import annotations

from datetime import UTC, datetime

from app.behavior.events import BehaviorEvent
from app.behavior.features import BehaviorFeatures, extract_features
from app.behavior.scoring import EventScorer
from app.behavior.track_state import TrackStore
from app.config import AnalysisRequest
from app.pipeline.frame_reader import VideoFrameReader
from app.pipeline.result_writer import write_json
from app.schemas.tracking import TrackObservation
from app.vision.sort_tracker import SortTracker
from app.vision.yolo_detector import YOLOPersonDetector


def analyze_video(request: AnalysisRequest) -> dict[str, object]:
    """Probe a video and write a Phase 1B analysis payload.

    Detection, tracking, and behavior scoring are added in later Phase 1 steps.
    This keeps the CLI useful while the pipeline is assembled incrementally.
    """

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
        detections = detector.detect(frame.image)
        observations = tracker.update(detections, frame.index, frame.timestamp_s)
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

    result: dict[str, object] = {
        "analysis_version": "phase-1f",
        "created_at": datetime.now(UTC).isoformat(),
        "video": metadata.to_dict(),
        "frames_processed": frames_processed,
        "frames": frame_summaries,
        "tracks": _summarize_tracks(all_observations, latest_features),
        "events": [event.to_dict() for event in events],
    }
    write_json(request.output_path, result)
    return result


def _summarize_tracks(
    observations: list[TrackObservation],
    features_by_track: dict[int, BehaviorFeatures],
) -> list[dict[str, object]]:
    summaries: dict[int, dict[str, object]] = {}
    for observation in observations:
        summary = summaries.setdefault(
            observation.track_id,
            {
                "track_id": observation.track_id,
                "observations": 0,
                "first_timestamp_s": observation.timestamp_s,
                "last_timestamp_s": observation.timestamp_s,
                "is_confirmed": False,
            },
        )
        summary["observations"] = int(summary["observations"]) + 1
        summary["last_timestamp_s"] = observation.timestamp_s
        summary["is_confirmed"] = bool(summary["is_confirmed"]) or observation.is_confirmed

    for track_id, features in features_by_track.items():
        summaries.setdefault(
            track_id,
            {
                "track_id": track_id,
                "observations": features.observations,
                "first_timestamp_s": 0.0,
                "last_timestamp_s": 0.0,
                "is_confirmed": features.is_confirmed,
            },
        )
        summaries[track_id]["features"] = features.to_dict()

    return list(summaries.values())
