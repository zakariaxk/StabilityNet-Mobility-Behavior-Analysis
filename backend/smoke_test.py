"""Backend smoke checks for StabilityNet.

The smoke test verifies the FastAPI app, local output directories, YOLO26n
model setup, and a tiny detector inference pass before testing a real MP4.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Callable

from fastapi.testclient import TestClient

logging.getLogger("app.main").setLevel(logging.ERROR)

from app.api.analysis_service import AnalysisService
from app.config import (
    DEFAULT_DETECTOR_DEVICE,
    DEFAULT_DETECTOR_MODEL,
    DETECTOR_DEVICE_ENV,
    DETECTOR_MODEL_ENV,
    DetectorConfig,
    detector_model_status,
)
from app.main import create_app
from app.vision.detector import DetectorDependencyError, DetectorInferenceError
from app.vision.yolo_detector import verify_yolo_detector

SAMPLE_VIDEO_ENV = "STABILITYNET_SAMPLE_VIDEO"
DEFAULT_SAMPLE_VIDEO = "samples/test-video.mp4"


class SmokeResult:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def pass_check(self, message: str) -> None:
        print(f"PASS {message}")

    def warn_check(self, message: str) -> None:
        self.warnings.append(message)
        print(f"WARN {message}")

    def fail_check(self, message: str) -> None:
        self.failures.append(message)
        print(f"FAIL {message}")


def main() -> int:
    result = SmokeResult()
    _run_check(result, "FastAPI app imports", _check_app_import)
    _run_check(result, "health endpoint works", _check_health)
    _run_check(result, "backend output directories exist", _check_directories)
    _check_model(result)
    _check_sample_video(result)
    _check_ffmpeg(result)

    if result.failures:
        print(f"\nSmoke test failed with {len(result.failures)} failure(s).")
        return 1

    warning_count = len(result.warnings)
    if warning_count:
        print(f"\nSmoke test passed with {warning_count} warning(s).")
    else:
        print("\nSmoke test passed.")
    return 0


def _run_check(result: SmokeResult, message: str, check: Callable[[], None]) -> None:
    try:
        check()
    except Exception as exc:
        result.fail_check(f"{message}: {exc}")
    else:
        result.pass_check(message)


def _check_app_import() -> None:
    create_app()


def _check_health() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    if response.status_code != 200:
        raise RuntimeError(f"expected HTTP 200, got {response.status_code}")
    payload = response.json()
    if payload.get("status") != "ok":
        raise RuntimeError(f"unexpected health payload: {payload}")


def _check_directories() -> None:
    service = AnalysisService()
    for directory in (service.output_dir, service.upload_dir, service.video_output_dir):
        directory.mkdir(parents=True, exist_ok=True)
        if not directory.exists() or not directory.is_dir():
            raise RuntimeError(f"directory is unavailable: {directory}")


def _check_model(result: SmokeResult) -> None:
    model_name = os.getenv(DETECTOR_MODEL_ENV, DEFAULT_DETECTOR_MODEL)
    device = os.getenv(DETECTOR_DEVICE_ENV, DEFAULT_DETECTOR_DEVICE)
    model_status = detector_model_status(model_name)
    if model_status.status == "missing" and model_status.can_auto_download:
        print(
            "INFO YOLO26n weights are missing; attempting automatic Ultralytics "
            f"download to {model_status.resolved_path}"
        )
    elif model_status.status == "missing":
        result.fail_check(
            model_status.message or f"Set {DETECTOR_MODEL_ENV} before real analysis."
        )
        return

    try:
        verification = verify_yolo_detector(
            DetectorConfig(model_name=model_name, device=device),
            run_inference=True,
        )
    except DetectorDependencyError as exc:
        result.fail_check(f"YOLO26n detector setup: {exc}")
        return
    except DetectorInferenceError as exc:
        result.fail_check(f"YOLO26n tiny inference pass: {exc}")
        return

    result.pass_check(f"YOLO26n model loaded successfully: {verification.model_path}")
    result.pass_check(f"inference device: {verification.device}")
    if verification.inference_ran:
        result.pass_check(
            "YOLO26n tiny inference pass completed "
            f"({verification.detections_count} detections on blank frame)"
        )


def _check_sample_video(result: SmokeResult) -> None:
    sample_path = Path(os.getenv(SAMPLE_VIDEO_ENV, DEFAULT_SAMPLE_VIDEO))
    if sample_path.exists():
        result.pass_check(f"sample video exists: {sample_path}")
        return
    result.warn_check(
        "sample video is missing. Uploads can still work, but sample-card analysis "
        f"needs {sample_path} or {SAMPLE_VIDEO_ENV}."
    )


def _check_ffmpeg(result: SmokeResult) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        result.pass_check(f"ffmpeg found: {ffmpeg}")
        return
    result.warn_check(
        "ffmpeg is not installed. Annotated browser-playable MP4 output requires "
        "ffmpeg H.264 transcoding."
    )


if __name__ == "__main__":
    raise SystemExit(main())
