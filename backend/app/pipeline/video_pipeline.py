"""High-level video analysis pipeline orchestration."""

from __future__ import annotations

from datetime import UTC, datetime

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

    frames_processed = 0
    frame_summaries: list[dict[str, object]] = []
    all_observations: list[TrackObservation] = []
    for frame in reader.frames(max_frames=request.config.max_frames):
        detections = detector.detect(frame.image)
        observations = tracker.update(detections, frame.index, frame.timestamp_s)
        all_observations.extend(observations)
        frame_summaries.append(
            {
                "frame_index": frame.index,
                "timestamp_s": frame.timestamp_s,
                "detections": [detection.to_dict() for detection in detections],
                "tracks": [observation.to_dict() for observation in observations],
            }
        )
        frames_processed += 1

    result: dict[str, object] = {
        "analysis_version": "phase-1d",
        "created_at": datetime.now(UTC).isoformat(),
        "video": metadata.to_dict(),
        "frames_processed": frames_processed,
        "frames": frame_summaries,
        "tracks": _summarize_tracks(all_observations),
        "events": [],
    }
    write_json(request.output_path, result)
    return result


def _summarize_tracks(observations: list[TrackObservation]) -> list[dict[str, object]]:
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

    return list(summaries.values())
