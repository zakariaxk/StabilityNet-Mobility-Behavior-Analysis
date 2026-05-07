"""Geometry helpers for detection and tracking."""

from __future__ import annotations

from app.schemas.detection import BoundingBox


def bbox_iou(left: BoundingBox, right: BoundingBox) -> float:
    x_left = max(left.x1, right.x1)
    y_top = max(left.y1, right.y1)
    x_right = min(left.x2, right.x2)
    y_bottom = min(left.y2, right.y2)

    intersection_width = max(0.0, x_right - x_left)
    intersection_height = max(0.0, y_bottom - y_top)
    intersection_area = intersection_width * intersection_height

    left_area = left.width * left.height
    right_area = right.width * right.height
    union_area = left_area + right_area - intersection_area

    if union_area <= 0:
        return 0.0
    return intersection_area / union_area

