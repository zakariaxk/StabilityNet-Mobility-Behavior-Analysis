# Copilot Instructions for StabilityNet

## Build, test, and lint commands

### Backend (`backend/`)

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
```

```bash
# Run API
uvicorn app.main:app --reload

# Run CLI analysis
python3 -m app.cli analyze --video samples/test-video.mp4 --output outputs/result.json
```

```bash
# Full backend test suite (tests are unittest.TestCase style, run via pytest — as CI does)
python3 -m pytest -q

# Single backend test file
python3 -m pytest -q tests/test_api.py

# Single backend test method
python3 -m pytest -q tests/test_api.py::ApiTests::test_rejects_missing_sample_path
```

```bash
# Detector + weights smoke test
python smoke_test.py
```

### Frontend (`frontend/`)

```bash
npm install
npm run dev
npm run lint
npm run typecheck
npm run build
npm run test
```

A Vitest-based frontend test script is configured in `frontend/package.json` (`npm run test`).

## High-level architecture

StabilityNet is a local two-app system:

1. **FastAPI backend** (`backend/app`) performs video analysis and writes persistent artifacts.
2. **Next.js frontend** (`frontend/src`) provides upload/sample UX and proxies all backend traffic through route handlers.

Backend request flow:

1. `app/api/routes.py` exposes `/health`, `/analyses`, `/analyses/upload`, `/analyses/{id}`, and `/analyses/{id}/video`.
2. `AnalysisService` (`app/api/analysis_service.py`) validates input paths/uploads, runs analysis, stores records under `outputs/analyses`, uploads under `outputs/uploads`, and annotated videos under `outputs/videos`.
3. `analyze_video` (`app/pipeline/video_pipeline.py`) orchestrates frame reading, YOLO person detection, SORT-style tracking, behavior feature extraction, event scoring, and annotated MP4 writing.
4. Results are normalized into a stable API shape (summary + result payload + compatibility fields like `annotated_video_url`/`video_url`).

Frontend request flow:

1. UI (`src/app/page.tsx`) calls `stabilityNetApi.ts`.
2. API helpers hit local Next route handlers under `src/app/api/stabilitynet/**`, not the backend directly.
3. Route handlers proxy to FastAPI via `backendProxy.ts`, including range-aware proxying for video streaming endpoints.
4. UI resolves video URL fields using fallback order in `analysisVideoUrl()` so older/newer backend payload variants still render.

## Key conventions specific to this repository

- **MP4-only contract** is strict across UI and API: uploads and sample analyses reject non-`.mp4` inputs.
- **Sample path security**: backend sample analysis only accepts paths inside `backend/samples` (no absolute paths or `..` traversal).
- **Backend output contract is compatibility-oriented**: keep `summary`, `result`, top-level counts, and video URL fields aligned when changing response payloads.
- **Detector configuration is env-driven and CPU-first by default**:
  - `STABILITYNET_DETECTOR_MODEL`
  - `STABILITYNET_DETECTOR_DEVICE` (defaults to `cpu`)
  - `yolo26n.pt` may auto-download if missing and default model name is used.
- **Frontend-backend integration should stay proxied through Next handlers** (`/api/stabilitynet/...`), including video routes to preserve browser streaming behavior.
- **Behavior events are human-labeled and severity-bucketed** in backend normalization/scoring (e.g., `Slow Walking`, `Prolonged Stop`, `Tracking Instability` with `low|medium|high`).
- **Backend tests use `unittest` style** with `test_*.py` modules and dependency injection/fake runners (especially for API tests) to avoid requiring full detector/video runtime in unit tests.
