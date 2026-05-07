"""High-level video analysis pipeline orchestration."""

from __future__ import annotations

from datetime import UTC, datetime

from app.config import AnalysisRequest
from app.pipeline.frame_reader import VideoFrameReader
from app.pipeline.result_writer import write_json


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

    frames_processed = 0
    for _frame in reader.frames(max_frames=request.config.max_frames):
        frames_processed += 1

    result: dict[str, object] = {
        "analysis_version": "phase-1b",
        "created_at": datetime.now(UTC).isoformat(),
        "video": metadata.to_dict(),
        "frames_processed": frames_processed,
        "tracks": [],
        "events": [],
    }
    write_json(request.output_path, result)
    return result

