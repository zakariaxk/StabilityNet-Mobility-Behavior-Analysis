"""Compatibility entrypoint for `uvicorn main:app` from the backend folder."""

from app.main import app, create_app

__all__ = ["app", "create_app"]
