"""Detection data structures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x1 + self.width / 2.0, self.y1 + self.height / 2.0)

    def to_xyxy(self) -> list[float]:
        return [self.x1, self.y1, self.x2, self.y2]

    def to_dict(self) -> dict[str, float | list[float]]:
        center_x, center_y = self.center
        return {
            "xyxy": self.to_xyxy(),
            "center": [center_x, center_y],
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class Detection:
    bbox: BoundingBox
    confidence: float
    class_id: int
    label: str = "person"

    def to_dict(self) -> dict[str, float | int | str | dict[str, float | list[float]]]:
        return {
            "bbox": self.bbox.to_dict(),
            "confidence": self.confidence,
            "class_id": self.class_id,
            "label": self.label,
        }

