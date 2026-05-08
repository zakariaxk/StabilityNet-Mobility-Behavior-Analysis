"""OpenCV-backed video frame ingestion."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from pathlib import Path
from typing import Any, Iterator

try:
    import cv2
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal envs.
    cv2 = None  # type: ignore[assignment]


class VideoOpenError(RuntimeError):
    """Raised when OpenCV cannot open the requested video."""


class VideoDependencyError(RuntimeError):
    """Raised when video ingestion dependencies are unavailable."""


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VideoMetadata:
    path: str
    fps: float
    frame_count: int
    width: int
    height: int
    duration_s: float

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "path": self.path,
            "fps": self.fps,
            "frame_count": self.frame_count,
            "width": self.width,
            "height": self.height,
            "duration_s": self.duration_s,
        }


@dataclass(frozen=True)
class VideoFrame:
    index: int
    timestamp_s: float
    image: Any


class VideoFrameReader:
    """Read frames from a video file with stable timestamps."""

    def __init__(self, video_path: Path, fallback_fps: float = 30.0) -> None:
        self.video_path = video_path
        self.fallback_fps = fallback_fps

    def metadata(self) -> VideoMetadata:
        capture = self._open_capture()
        try:
            cv = _require_cv2()
            fps = self._read_fps(capture)
            frame_count = _read_positive_int(capture.get(cv.CAP_PROP_FRAME_COUNT))
            width = _read_positive_int(capture.get(cv.CAP_PROP_FRAME_WIDTH))
            height = _read_positive_int(capture.get(cv.CAP_PROP_FRAME_HEIGHT))
            if width == 0 or height == 0:
                raise VideoOpenError("Video metadata is unreadable.")
            if frame_count == 0:
                logger.warning("video frame count is unavailable", extra={"path": str(self.video_path)})
            duration_s = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
            return VideoMetadata(
                path=str(self.video_path),
                fps=fps,
                frame_count=frame_count,
                width=width,
                height=height,
                duration_s=duration_s,
            )
        finally:
            capture.release()

    def frames(self, max_frames: int | None = None) -> Iterator[VideoFrame]:
        capture = self._open_capture()
        try:
            fps = self._read_fps(capture)
            index = 0
            while True:
                if max_frames is not None and index >= max_frames:
                    break

                ok, frame = capture.read()
                if not ok:
                    break

                timestamp_s = index / fps if fps > 0 else 0.0
                yield VideoFrame(index=index, timestamp_s=timestamp_s, image=frame)
                index += 1
        finally:
            capture.release()

    def _open_capture(self) -> Any:
        if not self.video_path.exists():
            raise VideoOpenError("Video file not found.")

        cv = _require_cv2()
        capture = cv.VideoCapture(str(self.video_path))
        if not capture.isOpened():
            capture.release()
            raise VideoOpenError("Could not open video file.")

        logger.info("video opened", extra={"path": str(self.video_path)})
        return capture

    def _read_fps(self, capture: Any) -> float:
        cv = _require_cv2()
        fps = float(capture.get(cv.CAP_PROP_FPS) or 0.0)
        if math.isfinite(fps) and fps > 0:
            return fps
        if math.isfinite(self.fallback_fps) and self.fallback_fps > 0:
            logger.warning(
                "video FPS is invalid; using fallback",
                extra={"path": str(self.video_path), "fallback_fps": self.fallback_fps},
            )
            return self.fallback_fps
        return 30.0


def _require_cv2() -> Any:
    if cv2 is None:
        raise VideoDependencyError(
            "OpenCV is required for video ingestion. Install backend dependencies "
            'with: python3 -m pip install -e ".[dev]"'
        )
    return cv2


def _read_positive_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isfinite(number) and number > 0:
            return int(number)
    return 0
