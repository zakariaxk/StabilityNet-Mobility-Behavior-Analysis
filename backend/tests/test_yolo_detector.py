import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import DetectorConfig
from app.vision.detector import DetectorDependencyError
from app.vision import yolo_detector
from app.vision.yolo_detector import YOLOPersonDetector, verify_yolo_detector


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
        device: str,
        verbose: bool,
    ) -> list[_FakeResult]:
        self.predict_calls.append(
            {
                "frame": frame,
                "conf": conf,
                "classes": classes,
                "device": device,
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
        yolo_detector._MODEL_CACHE.clear()

    def test_loads_configured_model_and_converts_person_detections(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "custom-yolo26.pt"
            model_path.write_bytes(b"fake weights")
            with patch.object(yolo_detector, "YOLO", _FakeYOLO):
                detector = YOLOPersonDetector(
                    DetectorConfig(
                        model_name=str(model_path),
                        confidence_threshold=0.42,
                        person_class_id=0,
                        device="cpu",
                    )
                )

                detections = detector.predict(frame="fake-frame")

        self.assertEqual(len(_FakeYOLO.instances), 1)
        model = _FakeYOLO.instances[0]
        self.assertEqual(model.model_name, str(model_path))
        self.assertEqual(
            model.predict_calls,
            [
                {
                    "frame": "fake-frame",
                    "conf": 0.42,
                    "classes": [0],
                    "device": "cpu",
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

    def test_missing_local_model_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "missing.pt"

            with self.assertRaisesRegex(
                DetectorDependencyError,
                "YOLO model weights not found",
            ):
                YOLOPersonDetector(DetectorConfig(model_name=str(missing_path)))

    def test_missing_yolo26n_downloads_to_configured_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "yolo26n.pt"

            def fake_download(path: Path) -> str:
                path.write_bytes(b"fake weights")
                return str(path)

            with patch.object(
                yolo_detector,
                "_download_official_yolo26n",
                side_effect=fake_download,
            ), patch.object(yolo_detector, "YOLO", _FakeYOLO):
                detector = YOLOPersonDetector(DetectorConfig(model_name=str(model_path)))

        self.assertEqual(detector.model_reference, str(model_path))
        self.assertEqual(len(_FakeYOLO.instances), 1)
        self.assertEqual(_FakeYOLO.instances[0].model_name, str(model_path))

    def test_reuses_loaded_model_for_same_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "custom-yolo26.pt"
            model_path.write_bytes(b"fake weights")
            with patch.object(yolo_detector, "YOLO", _FakeYOLO):
                YOLOPersonDetector(DetectorConfig(model_name=str(model_path)))
                YOLOPersonDetector(DetectorConfig(model_name=str(model_path)))

        self.assertEqual(len(_FakeYOLO.instances), 1)

    def test_verify_detector_runs_tiny_inference(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "custom-yolo26.pt"
            model_path.write_bytes(b"fake weights")
            with patch.object(yolo_detector, "YOLO", _FakeYOLO):
                verification = verify_yolo_detector(
                    DetectorConfig(model_name=str(model_path)),
                    run_inference=True,
                )

        self.assertEqual(verification.model_path, str(model_path))
        self.assertEqual(verification.device, "CPU")
        self.assertTrue(verification.inference_ran)
        self.assertEqual(verification.detections_count, 1)

    def test_rejects_unavailable_cuda_device(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "custom-yolo26.pt"
            model_path.write_bytes(b"fake weights")
            with patch.object(yolo_detector, "_cuda_available", return_value=False):
                with self.assertRaisesRegex(
                    DetectorDependencyError,
                    "CUDA is not available",
                ):
                    YOLOPersonDetector(
                        DetectorConfig(model_name=str(model_path), device="cuda")
                    )


if __name__ == "__main__":
    unittest.main()
