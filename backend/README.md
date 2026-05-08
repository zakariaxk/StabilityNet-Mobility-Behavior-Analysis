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

The CLI uses Ultralytics YOLO26n by default. To compare a different detector
weights file, pass `--detector-model`:

```bash
python3 -m app.cli analyze \
  --video path/to/video.mp4 \
  --output outputs/result.json \
  --detector-model yolo26s.pt
```

## Model Weights

The API expects YOLO weights at `backend/yolo26n.pt` by default. You can keep
weights somewhere else by setting `STABILITYNET_DETECTOR_MODEL` to an existing
`.pt` file:

```bash
export STABILITYNET_DETECTOR_MODEL=/absolute/path/to/yolo26n.pt
```

Relative `.pt` paths are resolved from the backend folder. If the file is
missing, the API returns HTTP 503 with the exact expected path and the env var
to set.

Check local readiness without running inference:

```bash
python smoke_test.py
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

Upload an MP4 directly:

```bash
curl -X POST http://127.0.0.1:8000/analyses/upload \
  -F "file=@/absolute/path/to/local-video.mp4;type=video/mp4"
```

Or use the local helper from the `backend` folder:

```bash
python test_video_upload.py /absolute/path/to/local-video.mp4
```

Both upload paths return JSON with an `annotated_video_url` when annotated
output was written. Open it by prefixing the backend host, for example:

```text
http://127.0.0.1:8000/outputs/<file>.mp4
```
