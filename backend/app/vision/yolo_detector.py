"""Ultralytics YOLO person detector implementation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from app.config import (
    DEFAULT_DETECTOR_DEVICE,
    DEFAULT_DETECTOR_MODEL,
    DETECTOR_DEVICE_ENV,
    DETECTOR_MODEL_ENV,
    DetectorConfig,
    YOLO26N_DOWNLOAD_URL,
    can_auto_download_detector_model,
    detector_model_missing_message,
    detector_model_path,
    is_local_detector_model_reference,
    resolve_detector_model_reference,
)
from app.pipeline.frame_reader import _require_cv2
from app.schemas.detection import BoundingBox, Detection
from app.vision.detector import DetectorDependencyError, DetectorInferenceError

try:
    from ultralytics import YOLO
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal envs.
    YOLO = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)
_MODEL_CACHE: dict[str, Any] = {}
_MODEL_CACHE_LOCK = Lock()
_ULTRALYTICS_ASSETS_RELEASE = "v8.4.0"


@dataclass(frozen=True)
class DetectorVerification:
    model_path: str
    device: str
    inference_ran: bool
    detections_count: int | None


class YOLOPersonDetector:
    """Detect people in frames using Ultralytics YOLO."""

    def __init__(self, config: DetectorConfig) -> None:
        if YOLO is None:
            raise DetectorDependencyError(
                "Ultralytics is required for YOLO detection. Install backend "
                'dependencies with: python3 -m pip install -e ".[dev]"'
            )
        self.config = config
        self.device = _select_inference_device(config.device)
        self.model_reference = _prepare_model_reference(config.model_name)
        self.model = _load_model(self.model_reference)
        logger.info(
            "inference device: %s",
            _device_label(self.device),
            extra={
                "device": self.device,
                "model_device": _model_device(self.model),
                "model_path": self.model_reference,
            },
        )

    def detect(self, frame: Any) -> list[Detection]:
        frame_for_inference, scale_x, scale_y = _prepare_analysis_frame(
            frame,
            target_width=self.config.analysis_width,
        )
        try:
            results = self.model.predict(
                frame_for_inference,
                conf=self.config.confidence_threshold,
                classes=[self.config.person_class_id],
                device=self.device,
                verbose=False,
            )
        except Exception as exc:
            raise DetectorInferenceError("YOLO inference failed while processing a frame.") from exc
        if not results:
            return []

        boxes = getattr(results[0], "boxes", None)
        if boxes is None:
            return []

        detections: list[Detection] = []
        for box in boxes:
            try:
                class_id = int(_tensor_item(box.cls))
                xyxy = _tensor_list(box.xyxy[0])
                confidence = float(_tensor_item(box.conf))
            except (TypeError, ValueError, IndexError) as exc:
                raise DetectorInferenceError("YOLO returned malformed detection output.") from exc
            if class_id != self.config.person_class_id:
                continue
            if len(xyxy) != 4:
                raise DetectorInferenceError("YOLO returned malformed bounding box output.")

            detections.append(
                Detection(
                    bbox=BoundingBox(
                        x1=float(xyxy[0]) * scale_x,
                        y1=float(xyxy[1]) * scale_y,
                        x2=float(xyxy[2]) * scale_x,
                        y2=float(xyxy[3]) * scale_y,
                    ),
                    confidence=confidence,
                    class_id=class_id,
                    label="person",
                )
            )
        return detections

    def predict(self, frame: Any) -> list[Detection]:
        """Compatibility alias for callers that expect a predict method."""

        return self.detect(frame)


def _tensor_item(value: Any) -> float:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "item"):
        return float(value.item())
    if isinstance(value, (list, tuple)):
        return float(value[0])
    return float(value)


def _tensor_list(value: Any) -> list[float]:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        return [float(item) for item in value.numpy().tolist()]
    if hasattr(value, "tolist"):
        return [float(item) for item in value.tolist()]
    return [float(item) for item in value]


def _prepare_analysis_frame(
    frame: Any,
    *,
    target_width: int | None,
) -> tuple[Any, float, float]:
    shape = getattr(frame, "shape", None)
    if (
        shape is None
        or not isinstance(shape, tuple)
        or len(shape) < 2
        or target_width is None
        or target_width <= 0
    ):
        return frame, 1.0, 1.0

    original_height = int(shape[0])
    original_width = int(shape[1])
    if original_width <= target_width or original_height <= 0:
        return frame, 1.0, 1.0

    resized_height = max(2, int(round(original_height * (target_width / original_width))))
    cv = _require_cv2()
    resized = cv.resize(frame, (target_width, resized_height), interpolation=cv.INTER_AREA)
    return resized, original_width / target_width, original_height / resized_height


def verify_yolo_detector(
    config: DetectorConfig,
    *,
    run_inference: bool = True,
) -> DetectorVerification:
    """Initialize the detector and optionally run a tiny inference pass."""

    detector = YOLOPersonDetector(config)
    detections_count: int | None = None
    if run_inference:
        try:
            import numpy as np
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency check.
            raise DetectorDependencyError(
                "NumPy is required for the YOLO smoke-test inference pass. Install "
                'backend dependencies with: python3 -m pip install -e ".[dev]"'
            ) from exc

        frame = np.zeros((32, 32, 3), dtype=np.uint8)
        detections_count = len(detector.predict(frame))

    return DetectorVerification(
        model_path=detector.model_reference,
        device=_device_label(detector.device),
        inference_ran=run_inference,
        detections_count=detections_count,
    )


def _load_model(model_reference: str) -> Any:
    with _MODEL_CACHE_LOCK:
        cached_model = _MODEL_CACHE.get(model_reference)
        if cached_model is not None:
            return cached_model
        logger.info(
            "loading YOLO26n model...",
            extra={"model_path": model_reference},
        )
        try:
            model = YOLO(model_reference)
        except Exception as exc:
            raise DetectorDependencyError(
                "Could not initialize YOLO26n model from "
                f"{model_reference}. Confirm that {DETECTOR_MODEL_ENV} points to "
                "a valid Ultralytics PyTorch .pt file, or download "
                f"{YOLO26N_DOWNLOAD_URL} and place it at "
                f"{detector_model_path(DEFAULT_DETECTOR_MODEL)}. Original error: {exc}"
            ) from exc
        _MODEL_CACHE[model_reference] = model
        logger.info(
            "model loaded successfully",
            extra={"model_path": model_reference},
        )
        return model


def _prepare_model_reference(model_name: str) -> str:
    _validate_model_reference(model_name)
    model_reference = resolve_detector_model_reference(model_name)
    if not is_local_detector_model_reference(model_name):
        return model_reference

    model_path = detector_model_path(model_name)
    if model_path.exists():
        return str(model_path)

    if can_auto_download_detector_model(model_name):
        return _download_official_yolo26n(model_path)

    raise DetectorDependencyError(detector_model_missing_message(model_name))


def _validate_model_reference(model_name: str) -> None:
    if not model_name.strip():
        raise DetectorDependencyError(
            "YOLO model weights are not configured. Set STABILITYNET_DETECTOR_MODEL."
        )

    if not is_local_detector_model_reference(model_name):
        return


def _download_official_yolo26n(model_path: Path) -> str:
    logger.info(
        "YOLO26n model weights missing; attempting automatic download",
        extra={
            "model_path": str(model_path),
            "download_url": YOLO26N_DOWNLOAD_URL,
        },
    )
    try:
        from ultralytics.utils.downloads import attempt_download_asset
    except Exception as exc:  # pragma: no cover - import failure covered by load.
        raise DetectorDependencyError(
            "Ultralytics automatic weight download is unavailable. Manually "
            f"download {YOLO26N_DOWNLOAD_URL} and place it at {model_path}."
        ) from exc

    model_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        downloaded_path = Path(
            attempt_download_asset(
                str(model_path),
                release=_ULTRALYTICS_ASSETS_RELEASE,
                progress=False,
            )
        )
    except Exception as exc:
        raise DetectorDependencyError(
            "Automatic YOLO26n weight download failed. Manually download "
            f"{YOLO26N_DOWNLOAD_URL} and place it at {model_path}, or set "
            f"{DETECTOR_MODEL_ENV} to an existing .pt file. Original error: {exc}"
        ) from exc

    if not downloaded_path.exists():
        raise DetectorDependencyError(
            "Automatic YOLO26n weight download did not create the expected file. "
            f"Manually download {YOLO26N_DOWNLOAD_URL} and place it at {model_path}, "
            f"or set {DETECTOR_MODEL_ENV} to an existing .pt file."
        )

    logger.info(
        "YOLO26n weights downloaded",
        extra={"model_path": str(downloaded_path)},
    )
    return str(downloaded_path)


def _select_inference_device(device: str) -> str:
    requested = (device or DEFAULT_DETECTOR_DEVICE).strip().lower()
    if requested in {"", "cpu"}:
        return "cpu"

    if requested == "auto":
        return _best_available_device()

    if requested == "mps":
        if _mps_available():
            return "mps"
        raise DetectorDependencyError(
            f"{DETECTOR_DEVICE_ENV}=mps was requested, but PyTorch MPS is not "
            "available. Use STABILITYNET_DETECTOR_DEVICE=cpu for the CPU-first demo."
        )

    if requested == "cuda" or requested.startswith("cuda:") or requested.isdigit():
        if _cuda_available():
            return requested
        raise DetectorDependencyError(
            f"{DETECTOR_DEVICE_ENV}={device} was requested, but CUDA is not "
            "available. Use STABILITYNET_DETECTOR_DEVICE=cpu for the CPU-first demo."
        )

    raise DetectorDependencyError(
        f"Unsupported {DETECTOR_DEVICE_ENV} value: {device}. Use cpu, auto, mps, "
        "cuda, cuda:0, or a CUDA device index."
    )


def _best_available_device() -> str:
    if _cuda_available():
        return "cuda"
    if _mps_available():
        return "mps"
    return "cpu"


def _cuda_available() -> bool:
    try:
        import torch
    except Exception:
        return False
    return bool(torch.cuda.is_available())


def _mps_available() -> bool:
    try:
        import torch
    except Exception:
        return False
    mps = getattr(torch.backends, "mps", None)
    return bool(mps is not None and mps.is_available())


def _device_label(device: str) -> str:
    normalized = device.lower()
    if normalized == "cpu":
        return "CPU"
    if normalized == "mps":
        return "MPS"
    if normalized == "cuda" or normalized.startswith("cuda:") or normalized.isdigit():
        return "CUDA"
    return device


def _model_device(model: Any) -> str:
    device = getattr(model, "device", None)
    if device is not None:
        return str(device)

    inner_model = getattr(model, "model", None)
    parameters = getattr(inner_model, "parameters", None)
    if callable(parameters):
        try:
            first_parameter = next(parameters())
        except StopIteration:
            return "unknown"
        except Exception:
            return "unknown"
        return str(getattr(first_parameter, "device", "unknown"))

    return "unknown"
