"""FastAPI routes for local video analysis."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.api.analysis_service import (
    AnalysisNotFoundError,
    AnalysisService,
    InvalidUploadError,
)
from app.api.schemas import AnalysisCreateRequest, AnalysisRecord
from app.pipeline.annotated_video import VideoWriteError
from app.pipeline.frame_reader import VideoDependencyError, VideoOpenError
from app.pipeline.video_pipeline import AnalysisPipelineError
from app.vision.detector import DetectorDependencyError, DetectorInferenceError

router = APIRouter()
logger = logging.getLogger(__name__)

MP4_CONTENT_TYPES = {
    "",
    "application/mp4",
    "application/octet-stream",
    "video/mp4",
    "video/x-m4v",
}
NO_VIDEO_MESSAGE = "Upload an MP4 file or select a sample video before running analysis."


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/analyses",
    response_model=AnalysisRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_analysis(
    payload: AnalysisCreateRequest,
    request: Request,
) -> dict[str, object]:
    service = _analysis_service(request)
    logger.info("analysis sample request received")
    try:
        return service.create(payload.video_path)
    except VideoOpenError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DetectorDependencyError, VideoDependencyError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DetectorInferenceError as exc:
        logger.exception("analysis inference failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except AnalysisPipelineError as exc:
        logger.exception("analysis pipeline failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except VideoWriteError as exc:
        logger.exception("analysis video output failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/analyses/upload",
    response_model=AnalysisRecord,
    status_code=status.HTTP_201_CREATED,
)
def upload_analysis(
    request: Request,
    file: UploadFile | None = File(None),
) -> dict[str, object]:
    service = _analysis_service(request)
    logger.info("analysis upload request received")
    if file is None:
        raise HTTPException(status_code=400, detail=NO_VIDEO_MESSAGE)
    if not _is_mp4_upload(file):
        raise HTTPException(status_code=400, detail="Only MP4 video uploads are supported.")

    try:
        return service.create_from_upload(file.filename, file.file)
    except (InvalidUploadError, VideoOpenError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DetectorDependencyError, VideoDependencyError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DetectorInferenceError as exc:
        logger.exception("upload analysis inference failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except AnalysisPipelineError as exc:
        logger.exception("upload analysis pipeline failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except VideoWriteError as exc:
        logger.exception("upload analysis video output failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/analyses/{analysis_id}", response_model=AnalysisRecord)
def get_analysis(analysis_id: str, request: Request) -> dict[str, object]:
    service = _analysis_service(request)
    try:
        return service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/analyses/{analysis_id}/video")
def get_analysis_video(analysis_id: str, request: Request) -> FileResponse:
    service = _analysis_service(request)
    try:
        video_path = service.get_video_path(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(video_path, media_type="video/mp4", filename=video_path.name)


def _analysis_service(request: Request) -> AnalysisService:
    return request.app.state.analysis_service


def _is_mp4_upload(file: UploadFile) -> bool:
    filename = file.filename or ""
    if Path(filename).suffix.lower() != ".mp4":
        return False
    return (file.content_type or "") in MP4_CONTENT_TYPES
