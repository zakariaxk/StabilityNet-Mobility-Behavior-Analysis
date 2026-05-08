import io
import unittest
from pathlib import Path
from unittest.mock import patch

from app.cli import build_parser, main
from app.config import AnalysisRequest, DEFAULT_DETECTOR_MODEL


class CliTests(unittest.TestCase):
    def test_parser_accepts_detector_model_override(self) -> None:
        parser = build_parser()

        args = parser.parse_args(
            [
                "analyze",
                "--video",
                "samples/test-video.mp4",
                "--output",
                "outputs/result.json",
                "--detector-model",
                "yolo26s.pt",
            ]
        )

        self.assertEqual(args.detector_model, "yolo26s.pt")

    def test_parser_defaults_to_yolo26n_detector(self) -> None:
        parser = build_parser()

        args = parser.parse_args(
            [
                "analyze",
                "--video",
                "samples/test-video.mp4",
                "--output",
                "outputs/result.json",
            ]
        )

        self.assertEqual(args.detector_model, DEFAULT_DETECTOR_MODEL)

    def test_main_passes_selected_detector_model_to_analysis_request(self) -> None:
        requests: list[AnalysisRequest] = []

        def fake_analyze_video(request: AnalysisRequest) -> dict[str, object]:
            requests.append(request)
            return {"frames_processed": 7}

        with patch(
            "app.pipeline.video_pipeline.analyze_video",
            side_effect=fake_analyze_video,
        ), patch("sys.stdout", new_callable=io.StringIO):
            exit_code = main(
                [
                    "analyze",
                    "--video",
                    "samples/test-video.mp4",
                    "--output",
                    "outputs/result.json",
                    "--detector-model",
                    "custom-person.pt",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].video_path, Path("samples/test-video.mp4"))
        self.assertEqual(requests[0].output_path, Path("outputs/result.json"))
        self.assertEqual(requests[0].config.detector.model_name, "custom-person.pt")


if __name__ == "__main__":
    unittest.main()
