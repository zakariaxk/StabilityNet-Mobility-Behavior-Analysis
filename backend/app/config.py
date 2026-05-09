"""Runtime configuration for the offline analysis pipeline."""

import os
from dataclasses import dataclass
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DETECTOR_MODEL = "yolo26n.pt"
DETECTOR_MODEL_ENV = "STABILITYNET_DETECTOR_MODEL"
DEFAULT_DETECTOR_DEVICE = "cpu"
DETECTOR_DEVICE_ENV = "STABILITYNET_DETECTOR_DEVICE"
DETECTOR_ANALYSIS_WIDTH_ENV = "STABILITYNET_ANALYSIS_WIDTH"
ANALYSIS_FRAME_STRIDE_ENV = "STABILITYNET_ANALYSIS_FRAME_STRIDE"
ANALYSIS_TARGET_FPS_ENV = "STABILITYNET_ANALYSIS_TARGET_FPS"
DETECTION_CONF_THRESHOLD_ENV = "STABILITYNET_DETECTION_CONF_THRESHOLD"
MAX_RENDERED_LABELS_ENV = "STABILITYNET_MAX_RENDERED_LABELS"
DISPLAY_EVENT_LIMIT_ENV = "STABILITYNET_DISPLAY_EVENT_LIMIT"
ANNOTATED_OUTPUT_MAX_WIDTH_ENV = "STABILITYNET_ANNOTATED_OUTPUT_MAX_WIDTH"
YOLO26N_DOWNLOAD_URL = (
    "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt"
)

ANALYSIS_MAX_WIDTH = 640
ANALYSIS_TARGET_FPS = 22.0
DETECTION_CONF_THRESHOLD = 0.42
TRACK_MIN_HITS = 5
TRACK_MAX_AGE = 35
TRACK_IOU_THRESHOLD = 0.22
EVENT_MIN_TRACK_DURATION_SECONDS = 1.0
EVENT_MIN_CONFIDENCE = 0.50
MAX_RENDERED_LABELS_PER_FRAME = 5
DISPLAY_EVENT_LIMIT = 12
ANNOTATED_OUTPUT_MAX_WIDTH = 1280


@dataclass(frozen=True)
class DetectorConfig:
    model_name: str = DEFAULT_DETECTOR_MODEL
    confidence_threshold: float = DETECTION_CONF_THRESHOLD
    person_class_id: int = 0
    device: str = DEFAULT_DETECTOR_DEVICE
    analysis_width: int | None = ANALYSIS_MAX_WIDTH


@dataclass(frozen=True)
class TrackerConfig:
    max_age_frames: int = TRACK_MAX_AGE
    min_hits: int = TRACK_MIN_HITS
    iou_threshold: float = TRACK_IOU_THRESHOLD
    smoothing_alpha: float = 0.62
    center_distance_threshold_ratio: float = 0.75


@dataclass(frozen=True)
class BehaviorConfig:
    dwell_radius_px: float = 30.0
    dwell_time_threshold_s: float = 8.0
    slow_speed_threshold_px_s: float = 18.0
    unstable_variance_threshold_px2: float = 900.0
    feature_window_s: float = 5.0
    min_track_duration_s: float = EVENT_MIN_TRACK_DURATION_SECONDS
    min_event_confidence: float = EVENT_MIN_CONFIDENCE
    min_track_frames: int = 10
    event_cooldown_s: float = 2.5


@dataclass(frozen=True)
class PipelineConfig:
    detector: DetectorConfig = DetectorConfig()
    tracker: TrackerConfig = TrackerConfig()
    behavior: BehaviorConfig = BehaviorConfig()
    fallback_fps: float = 30.0
    analysis_frame_stride: int = 0
    analysis_target_fps: float = ANALYSIS_TARGET_FPS
    max_rendered_labels_per_frame: int = MAX_RENDERED_LABELS_PER_FRAME
    display_event_limit: int = DISPLAY_EVENT_LIMIT
    annotated_output_max_width: int | None = ANNOTATED_OUTPUT_MAX_WIDTH
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
    analysis_width = _positive_int_from_env(
        DETECTOR_ANALYSIS_WIDTH_ENV,
        default=ANALYSIS_MAX_WIDTH,
        minimum=160,
    )
    frame_stride = _int_from_env(ANALYSIS_FRAME_STRIDE_ENV, default=0, minimum=0)
    target_fps = _positive_float_from_env(
        ANALYSIS_TARGET_FPS_ENV,
        default=ANALYSIS_TARGET_FPS,
        minimum=1.0,
    )
    confidence_threshold = _positive_float_from_env(
        DETECTION_CONF_THRESHOLD_ENV,
        default=DETECTION_CONF_THRESHOLD,
        minimum=0.01,
    )
    max_rendered_labels = _positive_int_from_env(
        MAX_RENDERED_LABELS_ENV,
        default=MAX_RENDERED_LABELS_PER_FRAME,
        minimum=1,
    )
    display_event_limit = _positive_int_from_env(
        DISPLAY_EVENT_LIMIT_ENV,
        default=DISPLAY_EVENT_LIMIT,
        minimum=1,
    )
    annotated_output_max_width = _positive_int_from_env(
        ANNOTATED_OUTPUT_MAX_WIDTH_ENV,
        default=ANNOTATED_OUTPUT_MAX_WIDTH,
        minimum=320,
    )
    return PipelineConfig(
        detector=DetectorConfig(
            model_name=os.getenv(DETECTOR_MODEL_ENV, DEFAULT_DETECTOR_MODEL),
            device=os.getenv(DETECTOR_DEVICE_ENV, DEFAULT_DETECTOR_DEVICE),
            analysis_width=analysis_width,
            confidence_threshold=confidence_threshold,
        ),
        analysis_frame_stride=frame_stride,
        analysis_target_fps=target_fps,
        max_rendered_labels_per_frame=max_rendered_labels,
        display_event_limit=display_event_limit,
        annotated_output_max_width=annotated_output_max_width,
    )


def _positive_int_from_env(name: str, default: int, minimum: int) -> int:
    return _int_from_env(name, default=default, minimum=minimum)


def _int_from_env(name: str, default: int, minimum: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    if parsed < minimum:
        return default
    return parsed


def _positive_float_from_env(name: str, default: float, minimum: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        parsed = float(raw_value)
    except ValueError:
        return default
    if parsed < minimum:
        return default
    return parsed


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
