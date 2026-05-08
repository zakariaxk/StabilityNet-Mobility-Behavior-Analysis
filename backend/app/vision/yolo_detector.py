"""Ultralytics YOLO person detector implementation."""

from __future__ import annotations

import logging
from threading import Lock
from typing import Any

from app.config import (
    DetectorConfig,
    detector_model_missing_message,
    detector_model_path,
    is_local_detector_model_reference,
    resolve_detector_model_reference,
)
from app.schemas.detection import BoundingBox, Detection
from app.vision.detector import DetectorDependencyError, DetectorInferenceError

try:
    from ultralytics import YOLO
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal envs.
    YOLO = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)
_MODEL_CACHE: dict[str, Any] = {}
_MODEL_CACHE_LOCK = Lock()


class YOLOPersonDetector:
    """Detect people in frames using Ultralytics YOLO."""

    def __init__(self, config: DetectorConfig) -> None:
        _validate_model_reference(config.model_name)
        if YOLO is None:
            raise DetectorDependencyError(
                "Ultralytics is required for YOLO detection. Install backend "
                'dependencies with: python3 -m pip install -e ".[dev]"'
            )
        self.config = config
        self.model = _load_model(config.model_name)
        logger.info(
            "YOLO model ready",
            extra={
                "model_name": config.model_name,
                "device": _model_device(self.model),
            },
        )

    def detect(self, frame: Any) -> list[Detection]:
        try:
            results = self.model.predict(
                frame,
                conf=self.config.confidence_threshold,
                classes=[self.config.person_class_id],
                verbose=False,
            )
        except Exception as exc:
            raise DetectorInferenceError("YOLO inference failed while processing a frame.") from exc
        if not results:
            return []

        boxes = getattr(results[0], "boxes", None)
        if boxes is None:
            return []

        detections: list[Detection] = []
        for box in boxes:
            try:
                class_id = int(_tensor_item(box.cls))
                xyxy = _tensor_list(box.xyxy[0])
                confidence = float(_tensor_item(box.conf))
            except (TypeError, ValueError, IndexError) as exc:
                raise DetectorInferenceError("YOLO returned malformed detection output.") from exc
            if class_id != self.config.person_class_id:
                continue
            if len(xyxy) != 4:
                raise DetectorInferenceError("YOLO returned malformed bounding box output.")

            detections.append(
                Detection(
                    bbox=BoundingBox(
                        x1=float(xyxy[0]),
                        y1=float(xyxy[1]),
                        x2=float(xyxy[2]),
                        y2=float(xyxy[3]),
                    ),
                    confidence=confidence,
                    class_id=class_id,
                    label="person",
                )
            )
        return detections


def _tensor_item(value: Any) -> float:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "item"):
        return float(value.item())
    if isinstance(value, (list, tuple)):
        return float(value[0])
    return float(value)


def _tensor_list(value: Any) -> list[float]:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        return [float(item) for item in value.numpy().tolist()]
    if hasattr(value, "tolist"):
        return [float(item) for item in value.tolist()]
    return [float(item) for item in value]


def _load_model(model_name: str) -> Any:
    _validate_model_reference(model_name)
    model_reference = resolve_detector_model_reference(model_name)
    with _MODEL_CACHE_LOCK:
        cached_model = _MODEL_CACHE.get(model_reference)
        if cached_model is not None:
            return cached_model
        try:
            model = YOLO(model_reference)
        except Exception as exc:
            raise DetectorDependencyError(
                f"Could not load YOLO model weights: {model_reference}."
            ) from exc
        _MODEL_CACHE[model_reference] = model
        return model


def _validate_model_reference(model_name: str) -> None:
    if not model_name.strip():
        raise DetectorDependencyError(
            "YOLO model weights are not configured. Set STABILITYNET_DETECTOR_MODEL."
        )

    if not is_local_detector_model_reference(model_name):
        return

    model_path = detector_model_path(model_name)
    if not model_path.exists():
        raise DetectorDependencyError(detector_model_missing_message(model_name))


def _model_device(model: Any) -> str:
    device = getattr(model, "device", None)
    if device is not None:
        return str(device)

    inner_model = getattr(model, "model", None)
    parameters = getattr(inner_model, "parameters", None)
    if callable(parameters):
        try:
            first_parameter = next(parameters())
        except StopIteration:
            return "unknown"
        except Exception:
            return "unknown"
        return str(getattr(first_parameter, "device", "unknown"))

    return "unknown"
