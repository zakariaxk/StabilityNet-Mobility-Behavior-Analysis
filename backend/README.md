# StabilityNet Backend

Offline-first video mobility analysis backend for StabilityNet.

Phase 1 keeps the backend runnable from the command line while the core video
pipeline is developed. FastAPI, Redis, PostgreSQL, and the Next.js UI are deferred
until the analysis pipeline produces useful structured outputs.

## Development

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
python3 -m app.cli --help
python3 -m unittest discover -s tests
```

## Phase 1 Target

```bash
python3 -m app.cli analyze --video path/to/video.mp4 --output outputs/result.json
```

## Minimal API

Run the local API from the `backend` folder:

```bash
uvicorn app.main:app --reload
```

Submit a local video path:

```bash
curl -X POST http://127.0.0.1:8000/analyses \
  -H "Content-Type: application/json" \
  -d '{"video_path":"samples/test-video.mp4"}'
```

API records include a compact `summary` section with frame, track, and event
counts for UI clients.
