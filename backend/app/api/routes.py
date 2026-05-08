"""FastAPI routes for local video analysis."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.api.analysis_service import (
    AnalysisNotFoundError,
    AnalysisService,
    InvalidUploadError,
)
from app.api.schemas import AnalysisCreateRequest, AnalysisRecord
from app.pipeline.frame_reader import VideoDependencyError, VideoOpenError
from app.vision.detector import DetectorDependencyError

router = APIRouter()


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
    try:
        return service.create(Path(payload.video_path))
    except VideoOpenError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DetectorDependencyError, VideoDependencyError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/analyses/upload",
    response_model=AnalysisRecord,
    status_code=status.HTTP_201_CREATED,
)
def upload_analysis(
    request: Request,
    file: UploadFile = File(...),
) -> dict[str, object]:
    service = _analysis_service(request)
    if file.content_type not in {"video/mp4", "application/mp4", "video/x-m4v"}:
        raise HTTPException(status_code=400, detail="Only MP4 video uploads are supported.")

    try:
        return service.create_from_upload(file.filename, file.file)
    except (InvalidUploadError, VideoOpenError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DetectorDependencyError, VideoDependencyError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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
