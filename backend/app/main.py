"""Minimal FastAPI app placeholder for later API phases."""

from fastapi import FastAPI

app = FastAPI(title="StabilityNet API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

