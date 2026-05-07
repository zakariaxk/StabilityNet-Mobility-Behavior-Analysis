"""FastAPI routes for local video analysis."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status

from app.api.analysis_service import AnalysisNotFoundError, AnalysisService
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


@router.get("/analyses/{analysis_id}", response_model=AnalysisRecord)
def get_analysis(analysis_id: str, request: Request) -> dict[str, object]:
    service = _analysis_service(request)
    try:
        return service.get(analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _analysis_service(request: Request) -> AnalysisService:
    return request.app.state.analysis_service

