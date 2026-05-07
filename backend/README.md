# StabilityNet Backend

Offline-first video mobility analysis backend for StabilityNet.

Phase 1 keeps the backend runnable from the command line while the core video
pipeline is developed. FastAPI, Redis, PostgreSQL, and the React UI are deferred
until the analysis pipeline produces useful structured outputs.

## Development

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
python3 -m app.cli --help
pytest
```

## Phase 1 Target

```bash
python3 -m app.cli analyze --video path/to/video.mp4 --output outputs/result.json
```
