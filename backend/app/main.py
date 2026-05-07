"""FastAPI application for StabilityNet."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analysis_service import AnalysisService
from app.api.routes import router

DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]


def create_app(
    analysis_service: AnalysisService | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    app = FastAPI(title="StabilityNet API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or DEFAULT_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.analysis_service = analysis_service or AnalysisService()
    app.include_router(router)
    return app


app = create_app()
