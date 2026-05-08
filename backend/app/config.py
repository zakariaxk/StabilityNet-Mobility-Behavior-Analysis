"""Runtime configuration for the offline analysis pipeline."""

from dataclasses import dataclass
from pathlib import Path


DEFAULT_DETECTOR_MODEL = "yolo26n.pt"


@dataclass(frozen=True)
class DetectorConfig:
    model_name: str = DEFAULT_DETECTOR_MODEL
    confidence_threshold: float = 0.35
    person_class_id: int = 0


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
