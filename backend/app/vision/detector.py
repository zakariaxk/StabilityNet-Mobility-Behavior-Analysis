"""Detector interfaces and errors."""

from __future__ import annotations

from typing import Any, Protocol

from app.schemas.detection import Detection


class DetectorDependencyError(RuntimeError):
    """Raised when detector runtime dependencies are unavailable."""


class DetectorInferenceError(RuntimeError):
    """Raised when detector inference fails for a frame."""


class PersonDetector(Protocol):
    def detect(self, frame: Any) -> list[Detection]:
        """Return person detections for one video frame."""
