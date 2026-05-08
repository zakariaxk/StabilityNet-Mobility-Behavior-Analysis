# StabilityNet Backend

Offline-first video mobility analysis backend for StabilityNet.

The backend runs local MP4 analysis through FastAPI or the CLI. The detector
uses Ultralytics YOLO26n PyTorch weights, OpenCV frame IO, and SORT-style
tracking. It is CPU-first for local demos.

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

The CLI uses Ultralytics YOLO26n by default. To compare a different existing
detector weights file, pass `--detector-model`:

```bash
python3 -m app.cli analyze \
  --video path/to/video.mp4 \
  --output outputs/result.json \
  --detector-model yolo26s.pt
```

## Model Weights

The detector uses the Ultralytics package from `pyproject.toml`
(`ultralytics>=8.4.0`) and expects the YOLO26n detection weights file:

```text
yolo26n.pt
```

By default, the file should exist here:

```text
backend/yolo26n.pt
```

The smoke test and the first real detector initialization can auto-download the
official Ultralytics `yolo26n.pt` file to that path when internet access is
available. The cached file is ignored by git.

Manual download URL:

```text
https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt
```

You can keep weights somewhere else by setting `STABILITYNET_DETECTOR_MODEL` to
an existing `.pt` file:

```bash
export STABILITYNET_DETECTOR_MODEL=/absolute/path/to/yolo26n.pt
```

Relative `.pt` paths are resolved from the backend folder. If the file is
missing and it is not the official `yolo26n.pt` name, the API returns HTTP 503
with the exact expected path and the env var to set.

The demo defaults to CPU. To intentionally use another available PyTorch
device, set `STABILITYNET_DETECTOR_DEVICE` to `auto`, `mps`, `cuda`, `cuda:0`,
or a CUDA device index.

Verify the model loads and can run a tiny inference pass:

```bash
python smoke_test.py
```

Expected YOLO lines include:

```text
PASS YOLO26n model loaded successfully: /.../backend/yolo26n.pt
PASS inference device: CPU
PASS YOLO26n tiny inference pass completed
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
