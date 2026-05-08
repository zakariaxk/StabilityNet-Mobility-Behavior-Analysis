"""Synchronous local analysis service for the Phase 2 API."""

from __future__ import annotations

import json
import logging
import math
import re
import shutil
from pathlib import Path
from typing import BinaryIO, Callable
from uuid import UUID, uuid4

from app.config import AnalysisRequest, PipelineConfig
from app.pipeline.result_writer import write_json
from app.pipeline.video_pipeline import analyze_video

AnalysisRunner = Callable[[AnalysisRequest], dict[str, object]]
logger = logging.getLogger(__name__)


class AnalysisNotFoundError(RuntimeError):
    """Raised when a requested analysis record does not exist."""


class InvalidUploadError(RuntimeError):
    """Raised when an uploaded video is not accepted."""


class AnalysisService:
    """Run local video analysis and persist API records as JSON files."""

    def __init__(
        self,
        output_dir: Path | str = "outputs/analyses",
        upload_dir: Path | str = "outputs/uploads",
        config: PipelineConfig | None = None,
        runner: AnalysisRunner = analyze_video,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.upload_dir = Path(upload_dir)
        self.config = config or PipelineConfig()
        self._runner = runner
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def create(self, video_path: Path) -> dict[str, object]:
        analysis_id = str(uuid4())
        return self._run_analysis(
            analysis_id=analysis_id,
            video_path=video_path,
            source="local_path",
        )

    def create_from_upload(
        self,
        filename: str | None,
        content: BinaryIO,
    ) -> dict[str, object]:
        analysis_id = str(uuid4())
        safe_name = _safe_upload_filename(filename)
        upload_path = self.upload_dir / analysis_id / safe_name
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        with upload_path.open("wb") as output_file:
            shutil.copyfileobj(content, output_file)
        if upload_path.stat().st_size == 0:
            upload_path.unlink(missing_ok=True)
            raise InvalidUploadError("Uploaded MP4 file is empty.")
        logger.info(
            "upload saved",
            extra={
                "analysis_id": analysis_id,
                "upload_path": str(upload_path),
                "bytes": upload_path.stat().st_size,
            },
        )

        return self._run_analysis(
            analysis_id=analysis_id,
            video_path=upload_path,
            source="uploaded_file",
            original_filename=filename or safe_name,
            video_url=f"/analyses/{analysis_id}/video",
            uploaded_video_path=str(upload_path),
        )

    def get_video_path(self, analysis_id: str) -> Path:
        record = self.get(analysis_id)
        video_path = record.get("uploaded_video_path")
        if not isinstance(video_path, str):
            raise AnalysisNotFoundError(f"analysis video not found: {analysis_id}")

        path = Path(video_path)
        if not path.exists():
            raise AnalysisNotFoundError(f"analysis video not found: {analysis_id}")
        return path

    def _run_analysis(
        self,
        analysis_id: str,
        video_path: Path,
        source: str,
        original_filename: str | None = None,
        video_url: str | None = None,
        uploaded_video_path: str | None = None,
    ) -> dict[str, object]:
        result_path = self._result_path(analysis_id)
        request = AnalysisRequest(
            video_path=video_path,
            output_path=result_path,
            config=self.config,
        )
        result = self._runner(request)
        result = _normalize_result(result)

        record: dict[str, object] = {
            "analysis_id": analysis_id,
            "status": result["status"],
            "frames_processed": result["frames_processed"],
            "tracks_count": result["tracks_count"],
            "events_count": result["events_count"],
            "fps": result["fps"],
            "processing_fps": result["processing_fps"],
            "annotated_video_url": result["annotated_video_url"],
            "tracks": result["tracks"],
            "events": result["events"],
            "message": result["message"],
            "video_path": str(video_path),
            "result_path": str(result_path),
            "source": source,
            "summary": _summarize_result(result),
            "result": result,
        }
        if original_filename is not None:
            record["original_filename"] = original_filename
        if video_url is not None:
            record["video_url"] = video_url
        if uploaded_video_path is not None:
            record["uploaded_video_path"] = uploaded_video_path

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


def _safe_upload_filename(filename: str | None) -> str:
    if filename is None or not filename.strip():
        return "upload.mp4"

    name = Path(filename).name
    if Path(name).suffix.lower() != ".mp4":
        raise InvalidUploadError("Only .mp4 video uploads are supported.")

    stem = Path(name).stem
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-")
    if not safe_stem:
        safe_stem = "upload"
    return f"{safe_stem}.mp4"


def _summarize_result(result: dict[str, object]) -> dict[str, object]:
    tracks = _list_value(result.get("tracks"))
    events = _list_value(result.get("events"))
    frames_processed = result.get("frames_processed", 0)

    return {
        "frames_processed": frames_processed if isinstance(frames_processed, int) else 0,
        "processing_fps": _finite_number(result.get("processing_fps")),
        "track_count": len(tracks),
        "tracks_count": len(tracks),
        "confirmed_track_count": _confirmed_track_count(tracks),
        "event_count": len(events),
        "events_count": len(events),
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


def _normalize_result(result: dict[str, object]) -> dict[str, object]:
    payload = dict(result)
    video = payload.get("video")
    video_metadata = video if isinstance(video, dict) else {}
    frames_processed = _int_value(payload.get("frames_processed"), default=0)
    tracks = _normalize_tracks(payload.get("tracks"))
    events = _normalize_events(payload.get("events"))
    fps = _finite_number(payload.get("fps")) or _finite_number(video_metadata.get("fps"))

    payload["status"] = _string_value(payload.get("status")) or "completed"
    payload["frames_processed"] = frames_processed
    payload["tracks_count"] = _int_value(payload.get("tracks_count"), default=len(tracks))
    payload["events_count"] = _int_value(payload.get("events_count"), default=len(events))
    payload["fps"] = fps
    payload["processing_fps"] = _finite_number(payload.get("processing_fps"))
    payload["annotated_video_url"] = _string_value(payload.get("annotated_video_url"))
    payload["tracks"] = tracks
    payload["events"] = events
    payload["message"] = _string_value(payload.get("message"))
    return payload


def _normalize_tracks(value: object) -> list[dict[str, object]]:
    tracks: list[dict[str, object]] = []
    if not isinstance(value, list):
        return tracks

    for item in value:
        if not isinstance(item, dict):
            continue
        track = dict(item)
        features = track.get("features")
        feature_record = features if isinstance(features, dict) else {}
        track_id = _int_value(track.get("id"), default=None)
        if track_id is None:
            track_id = _int_value(track.get("track_id"), default=None)
        if track_id is None:
            continue

        first_timestamp = _finite_number(track.get("first_timestamp_s"))
        last_timestamp = _finite_number(track.get("last_timestamp_s"))
        duration_seconds = _finite_number(track.get("duration_seconds"))
        if duration_seconds is None:
            duration_seconds = _finite_number(feature_record.get("duration_s"))
        if duration_seconds is None and first_timestamp is not None and last_timestamp is not None:
            duration_seconds = max(0.0, last_timestamp - first_timestamp)

        frames = _int_value(track.get("frames"), default=None)
        if frames is None:
            frames = _int_value(track.get("observations"), default=None)
        if frames is None:
            frames = _int_value(feature_record.get("observations"), default=0)

        track["id"] = track_id
        track["track_id"] = track_id
        track["duration_seconds"] = duration_seconds if duration_seconds is not None else 0.0
        track["frames"] = frames
        track["avg_confidence"] = _finite_number(
            track.get("avg_confidence"),
            track.get("average_confidence"),
        )
        trajectory = track.get("trajectory")
        track["trajectory"] = trajectory if isinstance(trajectory, list) else []
        tracks.append(track)

    return tracks


def _normalize_events(value: object) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    if not isinstance(value, list):
        return events

    for item in value:
        if not isinstance(item, dict):
            continue
        event = dict(item)
        event_type = _event_type_label(_string_value(event.get("event_type")))
        time_seconds = _finite_number(event.get("time_seconds"), event.get("timestamp_s"))
        description = (
            _string_value(event.get("description"))
            or _string_value(event.get("reason"))
            or _default_event_description(event_type)
        )
        severity = _severity_value(event.get("severity"))

        event["time_seconds"] = time_seconds if time_seconds is not None else 0.0
        event["timestamp_s"] = time_seconds if time_seconds is not None else 0.0
        event["event_type"] = event_type
        event["description"] = description
        event["reason"] = description
        event["severity"] = severity
        events.append(event)

    return events


def _event_type_label(value: str | None) -> str:
    labels = {
        "low_mobility_speed": "Slow Walking",
        "prolonged_dwell": "Prolonged Stop",
        "high_position_variance": "Tracking Instability",
    }
    if value is None:
        return "Tracking Instability"
    return labels.get(value, value)


def _default_event_description(event_type: str) -> str:
    descriptions = {
        "Slow Walking": "Reduced movement speed detected.",
        "Prolonged Stop": "Prolonged stop detected.",
        "Direction Change": "Direction change detected.",
        "Tracking Instability": "Unstable tracking movement detected.",
        "Assistance Proximity": "Assistance proximity detected.",
    }
    return descriptions.get(event_type, "Mobility event detected.")


def _severity_value(value: object) -> str:
    if isinstance(value, str) and value.lower() in {"low", "medium", "high"}:
        return value.lower()
    return "low"


def _int_value(value: object, default: int | None = 0) -> int | None:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return int(value)
    return default


def _finite_number(*values: object) -> float | None:
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            number = float(value)
            if math.isfinite(number):
                return number
    return None


def _string_value(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
