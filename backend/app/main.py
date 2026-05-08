"""FastAPI application for StabilityNet."""

import os

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
ALLOWED_ORIGINS_ENV = "ALLOWED_ORIGINS"
FRONTEND_ORIGIN_ENV = "FRONTEND_ORIGIN"


def _cors_origins_from_env() -> list[str]:
    raw_origins = os.getenv(ALLOWED_ORIGINS_ENV) or os.getenv(FRONTEND_ORIGIN_ENV)
    if not raw_origins:
        return DEFAULT_CORS_ORIGINS
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return origins or DEFAULT_CORS_ORIGINS


def create_app(
    analysis_service: AnalysisService | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    origins = cors_origins or _cors_origins_from_env()
    app = FastAPI(title="StabilityNet API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials="*" not in origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.analysis_service = analysis_service or AnalysisService()
    app.include_router(router)
    return app


app = create_app()
