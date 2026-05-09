"""Annotated MP4 video writing helpers."""

from __future__ import annotations

import logging
import math
import shutil
import subprocess
from pathlib import Path
from types import TracebackType
from typing import Any

from app.behavior.events import BehaviorEvent
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
        detections: list[Detection],
        observations: list[TrackObservation],
        events: list[BehaviorEvent],
    ) -> None:
        if self.output_path is None:
            return

        if self._writer is None:
            self._open_writer(frame)

        annotated_frame = frame.copy()
        for detection in detections:
            _draw_box(
                annotated_frame,
                detection.bbox,
                (140, 140, 140),
                f"{detection.label} {detection.confidence:.2f}",
            )
        for observation in observations:
            color = (40, 180, 70) if observation.is_confirmed else (40, 170, 220)
            _draw_box(
                annotated_frame,
                observation.bbox,
                color,
                f"ID {observation.track_id} {observation.confidence:.2f}",
            )
        _draw_events(annotated_frame, events)

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
            completed = subprocess.run(command, check=True, capture_output=True, timeout=300)
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


def _draw_box(frame: Any, bbox: BoundingBox, color: tuple[int, int, int], label: str) -> None:
    cv = _require_cv2()
    x1, y1, x2, y2 = [int(value) for value in bbox.to_xyxy()]
    cv.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    text_y = max(16, y1 - 6)
    cv.putText(frame, label, (x1, text_y), cv.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


def _draw_events(frame: Any, events: list[BehaviorEvent]) -> None:
    if not events:
        return

    cv = _require_cv2()
    for index, event in enumerate(events[:3]):
        y = 24 + index * 24
        cv.putText(
            frame,
            f"{event.event_type}: {event.severity}",
            (16, y),
            cv.FONT_HERSHEY_SIMPLEX,
            0.65,
            (40, 220, 220),
            2,
        )
