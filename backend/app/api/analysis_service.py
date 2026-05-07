"""Synchronous local analysis service for the Phase 2 API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable
from uuid import UUID, uuid4

from app.config import AnalysisRequest, PipelineConfig
from app.pipeline.result_writer import write_json
from app.pipeline.video_pipeline import analyze_video

AnalysisRunner = Callable[[AnalysisRequest], dict[str, object]]


class AnalysisNotFoundError(RuntimeError):
    """Raised when a requested analysis record does not exist."""


class AnalysisService:
    """Run local video analysis and persist API records as JSON files."""

    def __init__(
        self,
        output_dir: Path | str = "outputs/analyses",
        config: PipelineConfig | None = None,
        runner: AnalysisRunner = analyze_video,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.config = config or PipelineConfig()
        self._runner = runner

    def create(self, video_path: Path) -> dict[str, object]:
        analysis_id = str(uuid4())
        result_path = self._result_path(analysis_id)
        request = AnalysisRequest(
            video_path=video_path,
            output_path=result_path,
            config=self.config,
        )
        result = self._runner(request)

        record: dict[str, object] = {
            "analysis_id": analysis_id,
            "status": "completed",
            "video_path": str(video_path),
            "result_path": str(result_path),
            "summary": _summarize_result(result),
            "result": result,
        }
        write_json(self._record_path(analysis_id), record)
        return record

    def get(self, analysis_id: str) -> dict[str, object]:
        record_path = self._record_path(analysis_id)
        if not record_path.exists():
            raise AnalysisNotFoundError(f"analysis not found: {analysis_id}")

        with record_path.open("r", encoding="utf-8") as record_file:
            payload = json.load(record_file)
        if not isinstance(payload, dict):
            raise AnalysisNotFoundError(f"analysis record is invalid: {analysis_id}")
        return payload

    def _record_path(self, analysis_id: str) -> Path:
        safe_id = _safe_uuid(analysis_id)
        return self.output_dir / f"{safe_id}.json"

    def _result_path(self, analysis_id: str) -> Path:
        safe_id = _safe_uuid(analysis_id)
        return self.output_dir / f"{safe_id}.result.json"


def _safe_uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise AnalysisNotFoundError(f"analysis not found: {value}") from exc


def _summarize_result(result: dict[str, object]) -> dict[str, object]:
    tracks = _list_value(result.get("tracks"))
    events = _list_value(result.get("events"))
    frames_processed = result.get("frames_processed", 0)

    return {
        "frames_processed": frames_processed if isinstance(frames_processed, int) else 0,
        "track_count": len(tracks),
        "confirmed_track_count": _confirmed_track_count(tracks),
        "event_count": len(events),
        "event_counts_by_type": _event_counts(events, "event_type"),
        "event_counts_by_severity": _event_counts(events, "severity"),
    }


def _list_value(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _confirmed_track_count(tracks: list[object]) -> int:
    return sum(
        1
        for track in tracks
        if isinstance(track, dict) and track.get("is_confirmed") is True
    )


def _event_counts(events: list[object], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        value = event.get(key)
        if not isinstance(value, str):
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts
