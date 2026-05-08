import unittest
from unittest.mock import patch

from app.config import DetectorConfig
from app.vision import yolo_detector
from app.vision.yolo_detector import YOLOPersonDetector


class _FakeBox:
    def __init__(self, class_id: int, xyxy: list[float], confidence: float) -> None:
        self.cls = [class_id]
        self.xyxy = [xyxy]
        self.conf = [confidence]


class _FakeResult:
    def __init__(self, boxes: list[_FakeBox]) -> None:
        self.boxes = boxes


class _FakeYOLO:
    instances: list["_FakeYOLO"] = []

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.predict_calls: list[dict[str, object]] = []
        _FakeYOLO.instances.append(self)

    def predict(
        self,
        frame: object,
        conf: float,
        classes: list[int],
        verbose: bool,
    ) -> list[_FakeResult]:
        self.predict_calls.append(
            {
                "frame": frame,
                "conf": conf,
                "classes": classes,
                "verbose": verbose,
            }
        )
        return [
            _FakeResult(
                [
                    _FakeBox(0, [10.0, 20.0, 30.0, 60.0], 0.91),
                    _FakeBox(2, [1.0, 2.0, 3.0, 4.0], 0.88),
                ]
            )
        ]


class YoloPersonDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeYOLO.instances = []

    def test_loads_configured_model_and_converts_person_detections(self) -> None:
        with patch.object(yolo_detector, "YOLO", _FakeYOLO):
            detector = YOLOPersonDetector(
                DetectorConfig(
                    model_name="custom-yolo26.pt",
                    confidence_threshold=0.42,
                    person_class_id=0,
                )
            )

            detections = detector.detect(frame="fake-frame")

        self.assertEqual(len(_FakeYOLO.instances), 1)
        model = _FakeYOLO.instances[0]
        self.assertEqual(model.model_name, "custom-yolo26.pt")
        self.assertEqual(
            model.predict_calls,
            [
                {
                    "frame": "fake-frame",
                    "conf": 0.42,
                    "classes": [0],
                    "verbose": False,
                }
            ],
        )

        self.assertEqual(len(detections), 1)
        detection = detections[0]
        self.assertEqual(detection.class_id, 0)
        self.assertEqual(detection.label, "person")
        self.assertEqual(detection.confidence, 0.91)
        self.assertEqual(detection.bbox.to_xyxy(), [10.0, 20.0, 30.0, 60.0])


if __name__ == "__main__":
    unittest.main()
