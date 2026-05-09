"""Pydantic schemas for Phase 2 API requests and responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnalysisCreateRequest(BaseModel):
    video_path: str | None = Field(
        None,
        description="Local path to a video file, such as samples/test-video.mp4.",
    )


class AnalysisRecord(BaseModel):
    analysis_id: str
    status: str
    frames_processed: int = 0
    tracks_count: int = 0
    events_count: int = 0
    fps: float | None = None
    source_fps: float | None = None
    source_video_fps: float | None = None
    playback_fps: float | None = None
    cpu_analysis_throughput_fps: float | None = None
    analysis_throughput_fps: float | None = None
    effective_analysis_fps: float | None = None
    end_to_end_processing_fps: float | None = None
    end_to_end_throughput_fps: float | None = None
    processing_fps: float | None = None
    frames_analyzed: int = 0
    raw_track_count: int = 0
    qualified_subject_count: int = 0
    raw_event_count: int = 0
    mobility_event_count: int = 0
    scene_reliability: str | None = None
    annotated_video_url: str | None = None
    tracks: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None
    source: str = "local_path"
    original_filename: str | None = None
    video_url: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any]
