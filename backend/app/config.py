"""Runtime configuration for the offline analysis pipeline."""

import os
from dataclasses import dataclass
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DETECTOR_MODEL = "yolo26n.pt"
DETECTOR_MODEL_ENV = "STABILITYNET_DETECTOR_MODEL"
DEFAULT_DETECTOR_DEVICE = "cpu"
DETECTOR_DEVICE_ENV = "STABILITYNET_DETECTOR_DEVICE"
YOLO26N_DOWNLOAD_URL = (
    "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt"
)


@dataclass(frozen=True)
class DetectorConfig:
    model_name: str = DEFAULT_DETECTOR_MODEL
    confidence_threshold: float = 0.35
    person_class_id: int = 0
    device: str = DEFAULT_DETECTOR_DEVICE


@dataclass(frozen=True)
class TrackerConfig:
    max_age_frames: int = 20
    min_hits: int = 3
    iou_threshold: float = 0.3


@dataclass(frozen=True)
class BehaviorConfig:
    dwell_radius_px: float = 30.0
    dwell_time_threshold_s: float = 8.0
    slow_speed_threshold_px_s: float = 18.0
    unstable_variance_threshold_px2: float = 900.0
    feature_window_s: float = 5.0
    min_track_duration_s: float = 1.0


@dataclass(frozen=True)
class PipelineConfig:
    detector: DetectorConfig = DetectorConfig()
    tracker: TrackerConfig = TrackerConfig()
    behavior: BehaviorConfig = BehaviorConfig()
    fallback_fps: float = 30.0
    max_frames: int | None = None


@dataclass(frozen=True)
class AnalysisRequest:
    video_path: Path
    output_path: Path
    config: PipelineConfig = PipelineConfig()
    annotated_video_path: Path | None = None
    annotated_video_url: str | None = None


@dataclass(frozen=True)
class DetectorModelStatus:
    status: str
    configured_value: str
    resolved_path: str | None
    message: str | None = None
    can_auto_download: bool = False
    download_url: str | None = None


def pipeline_config_from_env() -> PipelineConfig:
    return PipelineConfig(
        detector=DetectorConfig(
            model_name=os.getenv(DETECTOR_MODEL_ENV, DEFAULT_DETECTOR_MODEL),
            device=os.getenv(DETECTOR_DEVICE_ENV, DEFAULT_DETECTOR_DEVICE),
        ),
    )


def is_remote_detector_model_reference(model_name: str) -> bool:
    configured_value = model_name.strip().lower()
    return configured_value.startswith(("http://", "https://", "grpc://", "ul://"))


def is_local_detector_model_reference(model_name: str) -> bool:
    """Return whether the detector reference should resolve to a local file."""

    if is_remote_detector_model_reference(model_name):
        return False
    model_path = Path(model_name.strip())
    return model_path.suffix.lower() == ".pt"


def detector_model_path(model_name: str) -> Path:
    """Resolve a local detector model reference from the backend folder."""

    model_path = Path(model_name.strip()).expanduser()
    if model_path.is_absolute():
        return model_path
    return (BACKEND_ROOT / model_path).resolve()


def resolve_detector_model_reference(model_name: str) -> str:
    """Return the value passed to Ultralytics for a detector model reference."""

    configured_value = model_name.strip()
    if not configured_value or not is_local_detector_model_reference(configured_value):
        return configured_value
    return str(detector_model_path(configured_value))


def detector_model_missing_message(model_name: str) -> str:
    configured_value = model_name.strip() or "<empty>"
    expected_path = detector_model_path(
        model_name.strip() if model_name.strip() else DEFAULT_DETECTOR_MODEL
    )
    if can_auto_download_detector_model(configured_value):
        return (
            "YOLO26n model weights not found. StabilityNet can auto-download "
            f"the official {DEFAULT_DETECTOR_MODEL} file to {expected_path} when "
            "the detector starts and internet access is available. Manual setup: "
            f"download {YOLO26N_DOWNLOAD_URL} and place it at {expected_path}, or "
            f"set {DETECTOR_MODEL_ENV} to an existing .pt file. Current "
            f"{DETECTOR_MODEL_ENV} value: {configured_value}."
        )
    return (
        "YOLO model weights not found. Place the weights file at "
        f"{expected_path} or set {DETECTOR_MODEL_ENV} to an existing .pt file. "
        f"Current {DETECTOR_MODEL_ENV} value: {configured_value}."
    )


def can_auto_download_detector_model(model_name: str) -> bool:
    configured_value = model_name.strip()
    if not configured_value:
        configured_value = DEFAULT_DETECTOR_MODEL
    return Path(configured_value).name == DEFAULT_DETECTOR_MODEL


def detector_model_status(model_name: str) -> DetectorModelStatus:
    configured_value = model_name.strip()
    if not configured_value:
        return DetectorModelStatus(
            status="missing",
            configured_value="<empty>",
            resolved_path=str(detector_model_path(DEFAULT_DETECTOR_MODEL)),
            message=(
                "YOLO model weights are not configured. Set "
                f"{DETECTOR_MODEL_ENV} to an existing .pt file."
            ),
            can_auto_download=True,
            download_url=YOLO26N_DOWNLOAD_URL,
        )

    if not is_local_detector_model_reference(configured_value):
        return DetectorModelStatus(
            status="configured",
            configured_value=configured_value,
            resolved_path=None,
            message=None,
        )

    resolved_path = detector_model_path(configured_value)
    if resolved_path.exists():
        return DetectorModelStatus(
            status="ready",
            configured_value=configured_value,
            resolved_path=str(resolved_path),
            message=None,
            can_auto_download=can_auto_download_detector_model(configured_value),
            download_url=(
                YOLO26N_DOWNLOAD_URL
                if can_auto_download_detector_model(configured_value)
                else None
            ),
        )

    return DetectorModelStatus(
        status="missing",
        configured_value=configured_value,
        resolved_path=str(resolved_path),
        message=detector_model_missing_message(configured_value),
        can_auto_download=can_auto_download_detector_model(configured_value),
        download_url=(
            YOLO26N_DOWNLOAD_URL
            if can_auto_download_detector_model(configured_value)
            else None
        ),
    )
