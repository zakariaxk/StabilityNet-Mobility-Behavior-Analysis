"""Backend smoke checks for StabilityNet.

This script avoids running YOLO inference. It verifies that the FastAPI app can
import, health checks work, output directories are creatable, and local model or
sample-video configuration is understandable before testing a real MP4.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable

from fastapi.testclient import TestClient

from app.api.analysis_service import AnalysisService
from app.config import DEFAULT_DETECTOR_MODEL, DETECTOR_MODEL_ENV
from app.main import create_app

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
    model_path = Path(os.getenv(DETECTOR_MODEL_ENV, DEFAULT_DETECTOR_MODEL))
    if model_path.exists():
        result.pass_check(f"YOLO model file exists: {model_path}")
        return
    result.warn_check(
        "YOLO model file is missing. Place weights at "
        f"{model_path} or set {DETECTOR_MODEL_ENV} before real analysis."
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
        "ffmpeg is not installed. Annotated videos will use OpenCV mp4v output, "
        "which may be less browser-compatible."
    )


if __name__ == "__main__":
    raise SystemExit(main())
