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

from app.config import AnalysisRequest, PipelineConfig, pipeline_config_from_env
from app.pipeline.frame_reader import VideoOpenError
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
        video_output_dir: Path | str = "outputs/videos",
        sample_dir: Path | str = "samples",
        config: PipelineConfig | None = None,
        runner: AnalysisRunner = analyze_video,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.upload_dir = Path(upload_dir)
        self.video_output_dir = Path(video_output_dir)
        self.sample_dir = Path(sample_dir)
        self.config = config or pipeline_config_from_env()
        self._runner = runner
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.video_output_dir.mkdir(parents=True, exist_ok=True)

    def create(self, video_path: Path | str | None) -> dict[str, object]:
        analysis_id = str(uuid4())
        safe_video_path = self._resolve_sample_video_path(video_path)
        return self._run_analysis(
            analysis_id=analysis_id,
            video_path=safe_video_path,
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
        annotated_video_path = record.get("annotated_video_path")
        if isinstance(annotated_video_path, str):
            path = Path(annotated_video_path)
            if path.exists():
                return path

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
        annotated_video_path = self._annotated_video_path(analysis_id)
        annotated_video_url = self._annotated_video_url(annotated_video_path)
        request = AnalysisRequest(
            video_path=video_path,
            output_path=result_path,
            config=self.config,
            annotated_video_path=annotated_video_path,
            annotated_video_url=annotated_video_url,
        )
        result = self._runner(request)
        result = _normalize_result(result)
        public_result = _public_result(result)
        if annotated_video_path.exists():
            result["annotated_video_url"] = annotated_video_url
            public_result["annotated_video_url"] = annotated_video_url

        record: dict[str, object] = {
            "analysis_id": analysis_id,
            "status": result["status"],
            "frames_processed": result["frames_processed"],
            "tracks_count": result["tracks_count"],
            "events_count": result["events_count"],
            "fps": result["fps"],
            "source_video_fps": result["source_video_fps"],
            "source_fps": result["source_fps"],
            "playback_fps": result["playback_fps"],
            "cpu_analysis_throughput_fps": result["cpu_analysis_throughput_fps"],
            "analysis_throughput_fps": result["analysis_throughput_fps"],
            "analysis_inference_throughput_fps": result["analysis_inference_throughput_fps"],
            "effective_analysis_fps": result["effective_analysis_fps"],
            "sampled_analysis_fps": result["sampled_analysis_fps"],
            "end_to_end_processing_fps": result["end_to_end_processing_fps"],
            "end_to_end_throughput_fps": result["end_to_end_throughput_fps"],
            "processing_fps": result["processing_fps"],
            "analysis_frame_stride": result["analysis_frame_stride"],
            "analysis_stride_mode": result["analysis_stride_mode"],
            "analysis_resolution_width": result["analysis_resolution_width"],
            "annotated_output_max_width": result.get("annotated_output_max_width"),
            "frames_analyzed": result["frames_analyzed"],
            "analyzed_frames_count": result["analyzed_frames_count"],
            "raw_track_count": result["raw_track_count"],
            "qualified_subject_count": result["qualified_subject_count"],
            "raw_event_count": result["raw_event_count"],
            "mobility_event_count": result["mobility_event_count"],
            "scene_reliability": result["scene_reliability"],
            "scene_reliability_score": result["scene_reliability_score"],
            "scene_reliability_reasons": result["scene_reliability_reasons"],
            "timing_seconds": result["timing_seconds"],
            "timing_ms": result["timing_ms"],
            "processing_profile": result["processing_profile"],
            "annotated_video_url": result["annotated_video_url"],
            "tracks": result["tracks"],
            "qualified_tracks": result.get("qualified_tracks", []),
            "events": result["events"],
            "message": result["message"],
            "video_path": str(video_path),
            "result_path": str(result_path),
            "source": source,
            "summary": _summarize_result(result),
            "result": public_result,
        }
        if original_filename is not None:
            record["original_filename"] = original_filename
        if video_url is not None:
            record["video_url"] = video_url
        elif result["annotated_video_url"] is not None:
            record["video_url"] = f"/analyses/{analysis_id}/video"
        if result["annotated_video_url"] is not None:
            record["annotated_video_path"] = str(annotated_video_path)
        if uploaded_video_path is not None:
            record["uploaded_video_path"] = uploaded_video_path

        write_json(self._record_path(analysis_id), record)
        logger.info(
            "analysis record written",
            extra={
                "analysis_id": analysis_id,
                "result_path": str(result_path),
                "annotated_video_url": result["annotated_video_url"],
            },
        )
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

    def _annotated_video_path(self, analysis_id: str) -> Path:
        safe_id = _safe_uuid(analysis_id)
        return self.video_output_dir / f"{safe_id}.mp4"

    def _annotated_video_url(self, video_path: Path) -> str:
        return f"/outputs/{video_path.name}"

    def _resolve_sample_video_path(self, video_path: Path | str | None) -> Path:
        if video_path is None or not str(video_path).strip():
            raise VideoOpenError(
                "Upload an MP4 file or select a sample video before running analysis."
            )

        requested_path = Path(str(video_path).strip())
        if requested_path.is_absolute() or ".." in requested_path.parts:
            raise VideoOpenError("Video file not found.")
        if requested_path.suffix.lower() != ".mp4":
            raise VideoOpenError("Only MP4 video files are supported.")

        relative_path = requested_path
        if relative_path.parts and relative_path.parts[0] == self.sample_dir.name:
            relative_path = Path(*relative_path.parts[1:])
        if not relative_path.parts:
            raise VideoOpenError("Video file not found.")

        sample_root = self.sample_dir.resolve()
        resolved_path = (sample_root / relative_path).resolve()
        try:
            resolved_path.relative_to(sample_root)
        except ValueError as exc:
            raise VideoOpenError("Video file not found.") from exc

        if not resolved_path.exists() or not resolved_path.is_file():
            raise VideoOpenError("Video file not found.")
        return self.sample_dir / relative_path


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
    raw_track_count = _int_value(result.get("raw_track_count"), default=len(tracks))
    qualified_subject_count = _int_value(
        result.get("qualified_subject_count"),
        default=sum(1 for track in tracks if isinstance(track, dict) and track.get("qualified") is True),
    )
    if qualified_subject_count == 0 and not any(
        isinstance(track, dict) and "qualified" in track for track in tracks
    ):
        qualified_subject_count = len(tracks)

    return {
        "frames_processed": frames_processed if isinstance(frames_processed, int) else 0,
        "frames_analyzed": _int_value(
            result.get("frames_analyzed"),
            default=_int_value(result.get("analyzed_frames_count"), default=0),
        ),
        "source_video_fps": _finite_number(result.get("source_video_fps"), result.get("fps")),
        "source_fps": _finite_number(
            result.get("source_fps"),
            result.get("source_video_fps"),
            result.get("fps"),
        ),
        "playback_fps": _finite_number(
            result.get("playback_fps"),
            result.get("source_video_fps"),
            result.get("fps"),
        ),
        "cpu_analysis_throughput_fps": _finite_number(
            result.get("cpu_analysis_throughput_fps"),
            result.get("analysis_throughput_fps"),
        ),
        "analysis_throughput_fps": _finite_number(result.get("analysis_throughput_fps")),
        "analysis_inference_throughput_fps": _finite_number(
            result.get("analysis_inference_throughput_fps")
        ),
        "sampled_analysis_fps": _finite_number(result.get("sampled_analysis_fps")),
        "effective_analysis_fps": _finite_number(
            result.get("effective_analysis_fps"),
            result.get("sampled_analysis_fps"),
        ),
        "end_to_end_processing_fps": _finite_number(
            result.get("end_to_end_processing_fps"),
            result.get("end_to_end_throughput_fps"),
            result.get("processing_fps"),
        ),
        "end_to_end_throughput_fps": _finite_number(
            result.get("end_to_end_throughput_fps"),
            result.get("processing_fps"),
        ),
        "processing_fps": _finite_number(result.get("processing_fps")),
        "analysis_frame_stride": _int_value(result.get("analysis_frame_stride"), default=1),
        "analysis_resolution_width": _int_value(result.get("analysis_resolution_width"), default=0),
        "annotated_output_max_width": _int_value(
            result.get("annotated_output_max_width"),
            default=0,
        ),
        "analyzed_frames_count": _int_value(result.get("analyzed_frames_count"), default=0),
        "raw_track_count": raw_track_count,
        "qualified_subject_count": qualified_subject_count,
        "track_count": raw_track_count,
        "tracks_count": raw_track_count,
        "confirmed_track_count": _confirmed_track_count(tracks),
        "raw_event_count": _int_value(result.get("raw_event_count"), default=len(events)),
        "mobility_event_count": _int_value(result.get("mobility_event_count"), default=len(events)),
        "event_count": _int_value(result.get("mobility_event_count"), default=len(events)),
        "events_count": _int_value(result.get("mobility_event_count"), default=len(events)),
        "scene_reliability": _string_value(result.get("scene_reliability")),
        "scene_reliability_reasons": (
            result.get("scene_reliability_reasons")
            if isinstance(result.get("scene_reliability_reasons"), list)
            else []
        ),
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
    qualified_tracks = [track for track in tracks if track.get("qualified") is True]
    has_explicit_qualification = any("qualified" in track for track in tracks)
    fps = _finite_number(payload.get("fps")) or _finite_number(video_metadata.get("fps"))
    source_video_fps = _finite_number(
        payload.get("source_video_fps"),
        payload.get("source_fps"),
        fps,
    )
    playback_fps = _finite_number(
        payload.get("playback_fps"),
        payload.get("annotated_video_fps"),
        source_video_fps,
    )
    analysis_throughput_fps = _finite_number(
        payload.get("analysis_throughput_fps"),
        payload.get("cpu_analysis_throughput_fps"),
    )
    cpu_analysis_throughput_fps = _finite_number(
        payload.get("cpu_analysis_throughput_fps"),
        analysis_throughput_fps,
    )
    analysis_inference_throughput_fps = _finite_number(
        payload.get("analysis_inference_throughput_fps"),
        payload.get("sampled_inference_throughput_fps"),
    )
    sampled_analysis_fps = _finite_number(
        payload.get("sampled_analysis_fps"),
        payload.get("effective_analysis_fps"),
    )
    effective_analysis_fps = _finite_number(
        payload.get("effective_analysis_fps"),
        sampled_analysis_fps,
    )
    end_to_end_throughput_fps = _finite_number(
        payload.get("end_to_end_throughput_fps"),
        payload.get("end_to_end_processing_fps"),
        payload.get("processing_fps"),
    )
    end_to_end_processing_fps = _finite_number(
        payload.get("end_to_end_processing_fps"),
        end_to_end_throughput_fps,
    )
    analysis_frame_stride = _int_value(payload.get("analysis_frame_stride"), default=1)
    analysis_resolution_width = _int_value(payload.get("analysis_resolution_width"), default=0)
    annotated_output_max_width = _int_value(payload.get("annotated_output_max_width"), default=0)
    analyzed_frames_count = _int_value(
        payload.get("analyzed_frames_count"),
        default=_int_value(payload.get("frames_analyzed"), default=0),
    )
    frames_analyzed = _int_value(
        payload.get("frames_analyzed"),
        default=analyzed_frames_count,
    )
    timing_seconds = payload.get("timing_seconds")
    timing_ms = payload.get("timing_ms")
    raw_track_count = _int_value(payload.get("raw_track_count"), default=len(tracks))
    qualified_subject_count = _int_value(
        payload.get("qualified_subject_count"),
        default=(len(qualified_tracks) if has_explicit_qualification else len(tracks)),
    )
    raw_event_count = _int_value(payload.get("raw_event_count"), default=len(events))
    mobility_event_count = _int_value(payload.get("mobility_event_count"), default=len(events))

    payload["status"] = _string_value(payload.get("status")) or "completed"
    payload["frames_processed"] = frames_processed
    payload["frames_analyzed"] = frames_analyzed
    payload["tracks_count"] = _int_value(payload.get("tracks_count"), default=raw_track_count)
    payload["events_count"] = _int_value(payload.get("events_count"), default=mobility_event_count)
    payload["fps"] = fps
    payload["source_fps"] = _finite_number(payload.get("source_fps"), source_video_fps)
    payload["source_video_fps"] = source_video_fps
    payload["playback_fps"] = playback_fps
    payload["cpu_analysis_throughput_fps"] = cpu_analysis_throughput_fps
    payload["analysis_throughput_fps"] = analysis_throughput_fps
    payload["analysis_inference_throughput_fps"] = analysis_inference_throughput_fps
    payload["effective_analysis_fps"] = effective_analysis_fps
    payload["sampled_analysis_fps"] = sampled_analysis_fps
    payload["end_to_end_processing_fps"] = end_to_end_processing_fps
    payload["end_to_end_throughput_fps"] = end_to_end_throughput_fps
    payload["processing_fps"] = _finite_number(payload.get("processing_fps"), end_to_end_throughput_fps)
    payload["analysis_frame_stride"] = analysis_frame_stride if analysis_frame_stride else 1
    payload["analysis_stride_mode"] = _string_value(payload.get("analysis_stride_mode")) or "configured"
    payload["analysis_resolution_width"] = analysis_resolution_width
    payload["annotated_output_max_width"] = annotated_output_max_width
    payload["analyzed_frames_count"] = analyzed_frames_count
    payload["raw_track_count"] = raw_track_count
    payload["qualified_subject_count"] = qualified_subject_count
    payload["raw_event_count"] = raw_event_count
    payload["mobility_event_count"] = mobility_event_count
    payload["scene_reliability"] = _string_value(payload.get("scene_reliability")) or "Unknown"
    payload["scene_reliability_score"] = _finite_number(payload.get("scene_reliability_score"))
    scene_reasons = payload.get("scene_reliability_reasons")
    payload["scene_reliability_reasons"] = scene_reasons if isinstance(scene_reasons, list) else []
    payload["timing_seconds"] = timing_seconds if isinstance(timing_seconds, dict) else {}
    payload["timing_ms"] = timing_ms if isinstance(timing_ms, dict) else {}
    processing_profile = payload.get("processing_profile")
    payload["processing_profile"] = processing_profile if isinstance(processing_profile, dict) else {}
    payload["annotated_video_url"] = _string_value(payload.get("annotated_video_url"))
    payload["tracks"] = tracks
    payload["qualified_tracks"] = qualified_tracks if has_explicit_qualification else tracks
    payload["events"] = events
    payload["message"] = _string_value(payload.get("message"))
    return payload


def _public_result(result: dict[str, object]) -> dict[str, object]:
    payload = dict(result)
    video = payload.get("video")
    if isinstance(video, dict):
        public_video = dict(video)
        public_video.pop("path", None)
        payload["video"] = public_video
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
        track_id = _int_value(event.get("track_id"), default=0)
        description = (
            _string_value(event.get("description"))
            or _string_value(event.get("reason"))
            or _default_event_description(event_type)
        )
        severity = _severity_value(event.get("severity"))

        event["time_seconds"] = time_seconds if time_seconds is not None else 0.0
        event["timestamp_s"] = time_seconds if time_seconds is not None else 0.0
        event["track_id"] = track_id if track_id is not None else 0
        event["event_type"] = event_type
        event["description"] = description
        event["reason"] = description
        event["severity"] = severity
        events.append(event)

    return events


def _event_type_label(value: str | None) -> str:
    labels = {
        "low_mobility_speed": "Slow walking",
        "prolonged_dwell": "Movement anomaly",
        "high_position_variance": "Abrupt trajectory change",
        "Slow Walking": "Slow walking",
        "Prolonged Stop": "Movement anomaly",
        "Tracking Instability": "Abrupt trajectory change",
        "Subject leaving frame": "Track ended near frame boundary",
    }
    if value is None:
        return "Movement anomaly"
    return labels.get(value, value)


def _default_event_description(event_type: str) -> str:
    descriptions = {
        "Slow walking": "Slow, consistent walking pattern observed.",
        "Movement anomaly": "Movement anomaly detected; review in context.",
        "Direction Change": "Direction change detected.",
        "Abrupt trajectory change": "Abrupt trajectory change detected.",
        "Track ended near frame boundary": "Track ended near frame boundary.",
        "Insufficient visual evidence": "Not enough visual evidence for a strong conclusion.",
        "Camera motion uncertainty": "Camera motion may affect mobility interpretation.",
        "Assistance Proximity": "Assistance proximity detected.",
        "Fall-like motion event": "Fall-like motion evidence detected; requires review.",
    }
    return descriptions.get(event_type, "Mobility event detected.")


def _severity_value(value: object) -> str:
    if isinstance(value, str) and value.lower() in {
        "low",
        "normal",
        "medium",
        "high",
        "review_needed",
        "insufficient_evidence",
        "uncertain",
    }:
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
