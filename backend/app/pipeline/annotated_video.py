"""Annotated MP4 video writing helpers."""

from __future__ import annotations

import logging
import math
import shutil
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from types import TracebackType
from typing import Any

from app.behavior.events import BehaviorEvent
from app.behavior.features import BehaviorFeatures
from app.config import (
    ANNOTATED_OUTPUT_MAX_WIDTH,
    BehaviorConfig,
    MAX_RENDERED_LABELS_PER_FRAME,
)
from app.pipeline.frame_reader import _require_cv2
from app.schemas.detection import BoundingBox, Detection
from app.schemas.tracking import TrackObservation

logger = logging.getLogger(__name__)

FFMPEG_REQUIRED_MESSAGE = (
    "ffmpeg is required to create browser-compatible annotated MP4 output. "
    "Install ffmpeg and rerun the analysis."
)
FFMPEG_TRANSCODE_FAILED_MESSAGE = (
    "ffmpeg failed to convert annotated video to browser-compatible H.264 MP4. "
    "Check ffmpeg and rerun the analysis."
)


class VideoWriteError(RuntimeError):
    """Raised when annotated video output cannot be written."""


class AnnotatedVideoWriter:
    """Lazy OpenCV MP4 writer for annotated analysis frames."""

    def __init__(
        self,
        output_path: Path | None,
        fps: float,
        fallback_fps: float,
        behavior_config: BehaviorConfig | None = None,
        max_rendered_labels: int = MAX_RENDERED_LABELS_PER_FRAME,
        output_max_width: int | None = ANNOTATED_OUTPUT_MAX_WIDTH,
    ) -> None:
        self.output_path = output_path
        if math.isfinite(fps) and fps > 0:
            self.fps = fps
        elif math.isfinite(fallback_fps) and fallback_fps > 0:
            self.fps = fallback_fps
        else:
            self.fps = 30.0
        self._writer: Any | None = None
        self._temp_path: Path | None = None
        self._frames_written = 0
        self._compatibility_path: str | None = None
        self._behavior_config = behavior_config or BehaviorConfig()
        self._max_rendered_labels = max(1, max_rendered_labels)
        self._output_max_width = output_max_width
        self._track_centers: dict[int, list[tuple[int, int]]] = defaultdict(list)
        self._recent_status_until_s: dict[int, tuple[str, float]] = {}
        self.transcode_seconds: float = 0.0

    def __enter__(self) -> "AnnotatedVideoWriter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is None:
            self.close()
        else:
            self.abort()

    def write(
        self,
        frame: Any,
        detections: list[Detection] | None = None,
        observations: list[TrackObservation] | None = None,
        frame_features: dict[int, BehaviorFeatures] | None = None,
        events: list[BehaviorEvent] | None = None,
        total_events_count: int = 0,
        frame_index: int = 0,
        timestamp_s: float = 0.0,
        hud_source_fps: float | None = None,
        hud_processing_fps: float | None = None,
        hud_scene_reliability: str | None = None,
    ) -> None:
        if self.output_path is None:
            return

        output_frame, scale_x, scale_y = _prepare_output_frame(
            frame,
            max_width=self._output_max_width,
        )
        if self._writer is None:
            self._open_writer(output_frame)

        annotated_frame = output_frame.copy()
        frame_features = frame_features or {}
        events = events or []
        detections = detections or []
        observations = [
            _scale_observation(observation, scale_x=scale_x, scale_y=scale_y)
            for observation in (observations or [])
        ]
        self._update_recent_events(events, timestamp_s)

        # Detections are intentionally not drawn by default to keep labels readable
        # in the UI and reduce per-frame draw overhead.
        _ = detections
        overlay_style = _overlay_style(annotated_frame)
        label_track_ids = _select_label_track_ids(
            observations=observations,
            frame_features=frame_features,
            recent_status=self._recent_status_until_s,
            timestamp_s=timestamp_s,
            max_labels=self._max_rendered_labels,
            config=self._behavior_config,
        )
        occupied_labels: list[tuple[int, int, int, int]] = []

        for observation in observations:
            features = frame_features.get(observation.track_id)
            risk_tone = _risk_tone(
                observation=observation,
                features=features,
                config=self._behavior_config,
                recent_status=self._recent_status_until_s.get(observation.track_id),
                frame_size=(int(frame.shape[1]), int(frame.shape[0])),
                timestamp_s=timestamp_s,
            )
            color = _risk_color(risk_tone)
            state = _motion_state(observation=observation, features=features, config=self._behavior_config)
            self._append_track_center(observation.track_id, observation.center)
            _draw_trajectory(
                annotated_frame,
                color,
                self._track_centers.get(observation.track_id, []),
                overlay_style,
            )
            if observation.track_id in label_track_ids:
                label_drawn = _draw_labeled_box(
                    frame=annotated_frame,
                    bbox=observation.bbox,
                    color=color,
                    text_color=_label_text_color(risk_tone),
                    line_primary=f"Subject {observation.track_id} | {_status_label(risk_tone)}",
                    line_secondary=f"Conf {observation.confidence:.2f} | {state}",
                    style=overlay_style,
                    occupied_labels=occupied_labels,
                )
                if label_drawn:
                    continue
            _draw_compact_box(
                frame=annotated_frame,
                bbox=observation.bbox,
                color=color,
                label=f"{observation.track_id}",
                style=overlay_style,
            )

        _draw_hud(
            frame=annotated_frame,
            frame_index=frame_index,
            timestamp_s=timestamp_s,
            active_tracks=len(observations),
            total_events_count=total_events_count,
            source_fps=hud_source_fps,
            processing_fps=hud_processing_fps,
            scene_reliability=hud_scene_reliability,
            style=overlay_style,
        )

        self._writer.write(annotated_frame)
        self._frames_written += 1

    def close(self) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None

        if self.output_path is None or self._temp_path is None:
            return
        if self._frames_written == 0:
            self._temp_path.unlink(missing_ok=True)
            return

        self._finalize_output()
        logger.info(
            "annotated video written",
            extra={
                "output_path": str(self.output_path),
                "frames": self._frames_written,
                "compatibility_path": self._compatibility_path,
            },
        )

    def abort(self) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None
        if self._temp_path is not None:
            self._temp_path.unlink(missing_ok=True)

    def _open_writer(self, frame: Any) -> None:
        if self.output_path is None:
            return

        shape = getattr(frame, "shape", None)
        if shape is None or len(shape) < 2:
            raise VideoWriteError("Could not read frame dimensions for annotated video.")

        height = int(shape[0])
        width = int(shape[1])
        if width <= 0 or height <= 0:
            raise VideoWriteError("Could not read frame dimensions for annotated video.")

        cv = _require_cv2()
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.unlink(missing_ok=True)
        self._temp_path = self.output_path.with_name(f"{self.output_path.stem}.raw.mp4")
        self._temp_path.unlink(missing_ok=True)

        fourcc = cv.VideoWriter_fourcc(*"mp4v")
        self._writer = cv.VideoWriter(str(self._temp_path), fourcc, self.fps, (width, height))
        if not self._writer.isOpened():
            self._writer.release()
            self._writer = None
            raise VideoWriteError(
                "Could not open annotated video writer. Check OpenCV MP4 codec support."
            )

    def _finalize_output(self) -> None:
        if self.output_path is None or self._temp_path is None:
            return

        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            self._delete_video_outputs()
            logger.warning(
                "ffmpeg not found; annotated video output unavailable",
                extra={"output_path": str(self.output_path)},
            )
            raise VideoWriteError(FFMPEG_REQUIRED_MESSAGE)

        command = [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(self._temp_path),
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-vcodec",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(self.output_path),
        ]
        try:
            transcode_started_at = time.perf_counter()
            completed = subprocess.run(command, check=True, capture_output=True, timeout=300)
            self.transcode_seconds = time.perf_counter() - transcode_started_at
        except subprocess.CalledProcessError as exc:
            self._raise_transcode_error(f"ffmpeg exited with {exc.returncode}", exc.stderr)
        except (subprocess.SubprocessError, OSError) as exc:
            self._raise_transcode_error(str(exc), None)

        if not self.output_path.exists() or self.output_path.stat().st_size == 0:
            self._raise_transcode_error("ffmpeg produced no output", completed.stderr)

        self._compatibility_path = "ffmpeg-h264-yuv420p"
        logger.info(
            "ffmpeg transcode produced browser-compatible annotated video",
            extra={"output_path": str(self.output_path)},
        )
        self._temp_path.unlink(missing_ok=True)

    def _raise_transcode_error(self, error: str, stderr: bytes | None) -> None:
        stderr_text = ""
        if stderr:
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
        self._delete_video_outputs()
        logger.warning(
            "ffmpeg transcode failed; annotated video output unavailable",
            extra={
                "output_path": str(self.output_path) if self.output_path else None,
                "error": error,
                "stderr": stderr_text,
            },
        )
        raise VideoWriteError(FFMPEG_TRANSCODE_FAILED_MESSAGE)

    def _delete_video_outputs(self) -> None:
        if self._temp_path is not None:
            self._temp_path.unlink(missing_ok=True)
        if self.output_path is not None:
            self.output_path.unlink(missing_ok=True)

    def _append_track_center(self, track_id: int, center: tuple[float, float]) -> None:
        points = self._track_centers[track_id]
        points.append((int(center[0]), int(center[1])))
        if len(points) > 24:
            del points[: len(points) - 24]

    def _update_recent_events(self, events: list[BehaviorEvent], timestamp_s: float) -> None:
        for event in events:
            severity = event.severity.lower()
            if severity == "high":
                self._recent_status_until_s[event.track_id] = ("high", timestamp_s + 3.0)
            elif severity == "insufficient_evidence":
                self._recent_status_until_s[event.track_id] = (
                    "insufficient_evidence",
                    timestamp_s + 3.0,
                )
            elif severity in {"review_needed", "uncertain"}:
                self._recent_status_until_s[event.track_id] = ("review_needed", timestamp_s + 3.0)
            elif severity == "medium":
                self._recent_status_until_s[event.track_id] = ("medium", timestamp_s + 2.0)
        stale_ids = [
            track_id
            for track_id, (_status, until_s) in self._recent_status_until_s.items()
            if until_s < timestamp_s
        ]
        for track_id in stale_ids:
            self._recent_status_until_s.pop(track_id, None)


def _select_label_track_ids(
    *,
    observations: list[TrackObservation],
    frame_features: dict[int, BehaviorFeatures],
    recent_status: dict[int, tuple[str, float]],
    timestamp_s: float,
    max_labels: int,
    config: BehaviorConfig,
) -> set[int]:
    ranked: list[tuple[float, int]] = []
    for observation in observations:
        features = frame_features.get(observation.track_id)
        status = recent_status.get(observation.track_id)
        status_name = status[0] if status is not None and timestamp_s <= status[1] else ""
        priority = 100.0
        if status_name == "high":
            priority = 0.0
        elif status_name in {"review_needed", "medium"}:
            priority = 18.0
        elif observation.is_confirmed and features is not None:
            duration_bonus = min(20.0, features.duration_s * 4.0)
            confidence_bonus = observation.confidence * 16.0
            priority = 45.0 - duration_bonus - confidence_bonus
            if features.duration_s < config.min_track_duration_s:
                priority += 22.0
        elif observation.is_confirmed:
            priority = 55.0 - observation.confidence * 10.0

        if observation.confidence < 0.35 and status_name != "high":
            priority += 30.0
        ranked.append((priority, observation.track_id))

    ranked.sort(key=lambda item: (item[0], item[1]))
    return {track_id for _priority, track_id in ranked[:max_labels]}


def _prepare_output_frame(
    frame: Any,
    *,
    max_width: int | None,
) -> tuple[Any, float, float]:
    shape = getattr(frame, "shape", None)
    if (
        shape is None
        or len(shape) < 2
        or max_width is None
        or max_width <= 0
    ):
        return frame, 1.0, 1.0
    original_height = int(shape[0])
    original_width = int(shape[1])
    max_dimension = max(original_width, original_height)
    if max_dimension <= max_width:
        return frame, 1.0, 1.0
    scale = max_width / max_dimension
    resized_width = max(2, int(round(original_width * scale)))
    resized_height = max(2, int(round(original_height * scale)))
    cv = _require_cv2()
    resized = cv.resize(frame, (resized_width, resized_height), interpolation=cv.INTER_AREA)
    return resized, resized_width / original_width, resized_height / original_height


def _scale_observation(
    observation: TrackObservation,
    *,
    scale_x: float,
    scale_y: float,
) -> TrackObservation:
    if scale_x == 1.0 and scale_y == 1.0:
        return observation
    bbox = observation.bbox
    return TrackObservation(
        track_id=observation.track_id,
        bbox=BoundingBox(
            x1=bbox.x1 * scale_x,
            y1=bbox.y1 * scale_y,
            x2=bbox.x2 * scale_x,
            y2=bbox.y2 * scale_y,
        ),
        confidence=observation.confidence,
        frame_index=observation.frame_index,
        timestamp_s=observation.timestamp_s,
        is_confirmed=observation.is_confirmed,
    )


def _draw_box(frame: Any, bbox: BoundingBox, color: tuple[int, int, int], label: str) -> None:
    cv = _require_cv2()
    x1, y1, x2, y2 = [int(value) for value in bbox.to_xyxy()]
    cv.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    text_y = max(16, y1 - 6)
    cv.putText(frame, label, (x1, text_y), cv.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


def _draw_labeled_box(
    frame: Any,
    bbox: BoundingBox,
    color: tuple[int, int, int],
    text_color: tuple[int, int, int],
    line_primary: str,
    line_secondary: str,
    style: dict[str, float | int],
    occupied_labels: list[tuple[int, int, int, int]],
) -> bool:
    cv = _require_cv2()
    x1, y1, x2, y2 = [int(value) for value in bbox.to_xyxy()]
    box_thickness = int(style["box_thickness"])
    cv.rectangle(frame, (x1, y1), (x2, y2), color, box_thickness)

    font = cv.FONT_HERSHEY_SIMPLEX
    primary_scale = float(style["primary_scale"])
    secondary_scale = float(style["secondary_scale"])
    text_thickness = int(style["text_thickness"])
    label_padding = int(style["label_padding"])
    line_spacing = int(style["line_spacing"])

    (primary_width, primary_height), _ = cv.getTextSize(
        line_primary, font, primary_scale, text_thickness
    )
    (secondary_width, secondary_height), _ = cv.getTextSize(
        line_secondary, font, secondary_scale, text_thickness
    )
    label_width = max(primary_width, secondary_width) + label_padding * 2
    label_height = (
        primary_height
        + secondary_height
        + label_padding * 2
        + line_spacing
    )
    frame_height, frame_width = int(frame.shape[0]), int(frame.shape[1])

    label_x = max(4, min(x1, frame_width - label_width - 4))
    candidate_tops = [y1 - label_height - 8, y2 + 8, y1 + 8]
    label_top = None
    for candidate_top in candidate_tops:
        bounded_top = max(4, min(frame_height - label_height - 4, candidate_top))
        candidate_rect = (
            label_x,
            bounded_top,
            min(frame_width - 1, label_x + label_width),
            min(frame_height - 1, bounded_top + label_height),
        )
        if not any(_rects_overlap(candidate_rect, occupied) for occupied in occupied_labels):
            label_top = bounded_top
            break
    if label_top is None:
        return False
    label_bottom = min(frame_height - 1, label_top + label_height)
    label_right = min(frame_width - 1, label_x + label_width)
    occupied_labels.append((label_x, label_top, label_right, label_bottom))

    cv.rectangle(frame, (label_x, label_top), (label_right, label_bottom), color, -1)
    primary_y = label_top + label_padding + primary_height
    secondary_y = primary_y + line_spacing + secondary_height
    cv.putText(
        frame,
        line_primary,
        (label_x + label_padding, primary_y),
        font,
        primary_scale,
        text_color,
        text_thickness,
        cv.LINE_AA,
    )
    cv.putText(
        frame,
        line_secondary,
        (label_x + label_padding, secondary_y),
        font,
        secondary_scale,
        text_color,
        text_thickness,
        cv.LINE_AA,
    )
    return True


def _draw_compact_box(
    frame: Any,
    bbox: BoundingBox,
    color: tuple[int, int, int],
    label: str,
    style: dict[str, float | int],
) -> None:
    cv = _require_cv2()
    x1, y1, x2, y2 = [int(value) for value in bbox.to_xyxy()]
    cv.rectangle(frame, (x1, y1), (x2, y2), color, max(1, int(style["compact_box_thickness"])))
    font = cv.FONT_HERSHEY_SIMPLEX
    scale = float(style["compact_scale"])
    thickness = max(1, int(style["compact_text_thickness"]))
    (text_width, text_height), _ = cv.getTextSize(label, font, scale, thickness)
    frame_height, frame_width = int(frame.shape[0]), int(frame.shape[1])
    label_x = max(3, min(x1, frame_width - text_width - 8))
    label_y = max(text_height + 4, min(y1 + text_height + 4, frame_height - 4))
    cv.putText(
        frame,
        label,
        (label_x, label_y),
        font,
        scale,
        color,
        thickness,
        cv.LINE_AA,
    )


def _rects_overlap(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
) -> bool:
    return not (
        left[2] + 4 <= right[0]
        or right[2] + 4 <= left[0]
        or left[3] + 4 <= right[1]
        or right[3] + 4 <= left[1]
    )


def _draw_trajectory(
    frame: Any,
    color: tuple[int, int, int],
    points: list[tuple[int, int]],
    style: dict[str, float | int],
) -> None:
    if len(points) < 2:
        return

    cv = _require_cv2()
    line_thickness = int(style["trajectory_thickness"])
    point_radius = int(style["point_radius"])
    for previous, current in zip(points, points[1:], strict=False):
        cv.line(frame, previous, current, color, line_thickness, cv.LINE_AA)
    cv.circle(frame, points[-1], point_radius, color, -1, cv.LINE_AA)


def _draw_hud(
    frame: Any,
    frame_index: int,
    timestamp_s: float,
    active_tracks: int,
    total_events_count: int,
    source_fps: float | None,
    processing_fps: float | None,
    scene_reliability: str | None,
    style: dict[str, float | int],
) -> None:
    cv = _require_cv2()
    lines = [
        f"Time: {timestamp_s:.2f}s | Frame: {frame_index}",
        f"Active Tracks: {active_tracks}",
        f"Events Detected: {total_events_count}",
    ]
    if source_fps is not None or processing_fps is not None:
        source_text = f"{source_fps:.1f}" if source_fps is not None else "-"
        processing_text = f"{processing_fps:.1f}" if processing_fps is not None else "-"
        lines.append(f"Source FPS: {source_text} | CPU FPS: {processing_text}")
    if scene_reliability:
        lines.append(f"Scene Reliability: {scene_reliability}")
    font = cv.FONT_HERSHEY_SIMPLEX
    scale = float(style["hud_scale"])
    thickness = int(style["text_thickness"])
    hud_padding = int(style["hud_padding"])
    line_height = int(style["hud_line_height"])
    widths = [cv.getTextSize(line, font, scale, thickness)[0][0] for line in lines]
    panel_width = max(widths) + hud_padding * 2
    panel_height = hud_padding + line_height * len(lines) + 2
    panel_x = 12
    panel_y = 12

    cv.rectangle(
        frame,
        (panel_x, panel_y),
        (panel_x + panel_width, panel_y + panel_height),
        (18, 18, 18),
        -1,
    )
    for index, line in enumerate(lines):
        cv.putText(
            frame,
            line,
            (panel_x + hud_padding, panel_y + hud_padding + 2 + index * line_height),
            font,
            scale,
            (235, 235, 235),
            thickness,
            cv.LINE_AA,
        )


def _risk_tone(
    observation: TrackObservation,
    features: BehaviorFeatures | None,
    config: BehaviorConfig,
    recent_status: tuple[str, float] | None,
    frame_size: tuple[int, int],
    timestamp_s: float,
) -> str:
    # This is an explainable mobility risk indicator for annotation only, not diagnosis.
    rank = 0
    if recent_status is not None and timestamp_s <= recent_status[1]:
        status_rank = _status_rank(recent_status[0])
        rank = max(rank, status_rank)

    near_boundary = _bbox_near_boundary(
        observation.bbox,
        frame_width=frame_size[0],
        frame_height=frame_size[1],
    )
    if near_boundary and observation.confidence < 0.55:
        rank = max(rank, _status_rank("review_needed"))

    if observation.confidence < 0.45 or not observation.is_confirmed:
        rank = max(rank, _status_rank("insufficient_evidence"))

    if features is None:
        return _rank_to_status(rank)

    fall_like = (
        features.recent_vertical_delta_px >= 28.0
        and features.bbox_height_change_ratio >= 0.28
        and features.position_variance_px2 >= config.unstable_variance_threshold_px2 * 1.25
    )
    if fall_like:
        rank = max(rank, _status_rank("high"))
    elif features.position_variance_px2 >= config.unstable_variance_threshold_px2 * 1.25:
        rank = max(rank, _status_rank("review_needed"))

    if features.dwell_time_s >= config.dwell_time_threshold_s * 1.25:
        rank = max(rank, _status_rank("medium"))
    elif features.dwell_time_s >= config.dwell_time_threshold_s:
        rank = max(rank, _status_rank("review_needed"))

    if features.mean_speed_px_s <= config.slow_speed_threshold_px_s:
        rank = max(rank, _status_rank("review_needed"))
    if features.observations < 5:
        rank = max(rank, _status_rank("insufficient_evidence"))

    return _rank_to_status(rank)


def _motion_state(
    observation: TrackObservation,
    features: BehaviorFeatures | None,
    config: BehaviorConfig,
) -> str:
    if not observation.is_confirmed:
        return "acquiring"
    if features is None:
        return "walking"
    if features.position_variance_px2 >= config.unstable_variance_threshold_px2 * 1.25:
        return "review"
    if features.dwell_time_s >= config.dwell_time_threshold_s:
        return "stopped"
    if features.recent_speed_px_s <= config.slow_speed_threshold_px_s:
        return "slow"
    return "walking"


def _status_rank(status: str) -> int:
    if status == "high":
        return 4
    if status == "medium":
        return 3
    if status == "review_needed":
        return 2
    if status == "insufficient_evidence":
        return 1
    return 0


def _rank_to_status(rank: int) -> str:
    if rank >= 4:
        return "high"
    if rank >= 3:
        return "medium"
    if rank >= 2:
        return "review_needed"
    if rank >= 1:
        return "insufficient_evidence"
    return "low"


def _risk_color(risk_tone: str) -> tuple[int, int, int]:
    if risk_tone == "high":
        return (45, 55, 220)  # red
    if risk_tone == "medium":
        return (30, 190, 235)  # amber
    if risk_tone == "review_needed":
        return (36, 166, 220)  # amber
    if risk_tone == "insufficient_evidence":
        return (155, 126, 92)  # gray-blue
    return (75, 185, 95)  # teal-green


def _label_text_color(risk_tone: str) -> tuple[int, int, int]:
    if risk_tone == "medium":
        return (20, 20, 20)
    return (245, 245, 245)


def _status_label(status: str) -> str:
    if status == "high":
        return "Fall-like Motion"
    if status == "medium":
        return "Review Needed"
    if status == "review_needed":
        return "Review Needed"
    if status == "insufficient_evidence":
        return "Insufficient Evidence"
    return "Stable"


def _bbox_near_boundary(
    bbox: BoundingBox,
    *,
    frame_width: int,
    frame_height: int,
) -> bool:
    if frame_width <= 0 or frame_height <= 0:
        return False
    edge_margin_x = max(12.0, frame_width * 0.045)
    edge_margin_y = max(12.0, frame_height * 0.045)
    x1, y1, x2, y2 = bbox.to_xyxy()
    return bool(
        x1 <= edge_margin_x
        or y1 <= edge_margin_y
        or x2 >= frame_width - edge_margin_x
        or y2 >= frame_height - edge_margin_y
    )


def _overlay_style(frame: Any) -> dict[str, float | int]:
    height = int(frame.shape[0])
    width = int(frame.shape[1])
    min_dim = max(1, min(width, height))
    scale = max(0.95, min(2.2, min_dim / 900.0))
    return {
        "primary_scale": 0.60 * scale,
        "secondary_scale": 0.50 * scale,
        "text_thickness": max(1, int(round(1.6 * scale))),
        "box_thickness": max(2, int(round(3.2 * scale))),
        "compact_box_thickness": max(1, int(round(1.7 * scale))),
        "compact_scale": 0.45 * scale,
        "compact_text_thickness": max(1, int(round(1.1 * scale))),
        "trajectory_thickness": max(2, int(round(2.4 * scale))),
        "point_radius": max(3, int(round(3.5 * scale))),
        "label_padding": max(6, int(round(9 * scale))),
        "line_spacing": max(4, int(round(5 * scale))),
        "hud_scale": 0.56 * scale,
        "hud_padding": max(8, int(round(10 * scale))),
        "hud_line_height": max(18, int(round(22 * scale))),
    }
