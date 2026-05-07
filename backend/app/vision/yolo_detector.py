"""YOLOv8n person detector implementation."""

from __future__ import annotations

from typing import Any

from app.config import DetectorConfig
from app.schemas.detection import BoundingBox, Detection
from app.vision.detector import DetectorDependencyError

try:
    from ultralytics import YOLO
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal envs.
    YOLO = None  # type: ignore[assignment]


class YOLOPersonDetector:
    """Detect people in frames using Ultralytics YOLOv8."""

    def __init__(self, config: DetectorConfig) -> None:
        if YOLO is None:
            raise DetectorDependencyError(
                "Ultralytics is required for YOLO detection. Install backend "
                'dependencies with: python3 -m pip install -e ".[dev]"'
            )
        self.config = config
        self.model = YOLO(config.model_name)

    def detect(self, frame: Any) -> list[Detection]:
        results = self.model.predict(
            frame,
            conf=self.config.confidence_threshold,
            classes=[self.config.person_class_id],
            verbose=False,
        )
        if not results:
            return []

        boxes = getattr(results[0], "boxes", None)
        if boxes is None:
            return []

        detections: list[Detection] = []
        for box in boxes:
            class_id = int(_tensor_item(box.cls))
            if class_id != self.config.person_class_id:
                continue

            xyxy = _tensor_list(box.xyxy[0])
            detections.append(
                Detection(
                    bbox=BoundingBox(
                        x1=float(xyxy[0]),
                        y1=float(xyxy[1]),
                        x2=float(xyxy[2]),
                        y2=float(xyxy[3]),
                    ),
                    confidence=float(_tensor_item(box.conf)),
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

