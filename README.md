# StabilityNet

Video-based human mobility analysis system. Ingests MP4 video, runs person detection and multi-object tracking, extracts temporal motion features per tracked subject, scores those features against configurable thresholds, and produces an annotated output video alongside a structured JSON analysis record. A Next.js frontend provides upload, playback, and result inspection. The full pipeline runs locally with no cloud dependency.

---

## How It Works

```
MP4 input
  → OpenCV frame reader          (decode, metadata, FPS)
  → YOLO26n person detector      (bounding boxes + confidence per frame)
  → SORT-style tracker           (IoU + center-distance matching, stable IDs)
  → TrackHistory accumulation    (per-track temporal point store)
  → Feature extraction           (speed, variance, dwell, posture, direction)
  → Heuristic event scoring      (threshold-based severity classification)
  → AnnotatedVideoWriter         (OpenCV overlay → ffmpeg H.264/yuv420p)
  → JSON analysis record         (tracks, events, timing, scene metadata)
```

Every component is independently testable. The pipeline has no dependency on the API layer — FastAPI routes call `analyze_video()` as a function, not the other way around.

---

## Detection

**Model:** YOLO26n via Ultralytics (`ultralytics>=8.4.0`), the nano-footprint variant from the v8.4.0 release. Detects persons (class 0) only. Bounding boxes and confidence scores are the only output consumed downstream.

**Analysis resolution:** frames are downscaled to a max width of 640px before inference to control CPU throughput. The original frame is used for annotation output (up to 1280px wide).

**Frame sampling:** at high source FPS, the pipeline computes an effective analysis stride so that analysis runs at approximately 22 FPS regardless of source frame rate. Every frame is written to the annotated output; only analysis-stride frames run detection and tracking. Non-analysis frames reuse the previous observation set with a small confidence decay (0.96×).

**Confidence threshold:** 0.35. Detections below this are discarded before tracking.

**Device:** CPU by default. Override with `STABILITYNET_DETECTOR_DEVICE=mps|cuda|cuda:0|auto`.

---

## Tracking

**Algorithm:** SORT-style greedy IoU + center-distance matching. No Kalman filter; no Hungarian assignment. Each frame, every live track is scored against every new detection using:

```
match_score = max(IoU(track_bbox, detection_bbox), center_distance_score)
```

The center-distance score normalizes displacement against the larger of the two bbox dimensions, scaled by a configurable ratio (default 0.75). This lets tracks survive large bbox shape changes (e.g., person bending over) that would otherwise break pure IoU matching.

**Track lifecycle:**
- A new unmatched detection creates a new track with `hits=1`, `missed_frames=0`
- `is_confirmed` requires `hits >= 3` consecutive observations (downstream gate for event scoring)
- An unmatched track increments `missed_frames`; it is dropped at `missed_frames > 20`
- Track IDs are monotonically increasing integers, never reused within a session

**Smoothing:** matched bbox coordinates are exponentially smoothed with `alpha=0.62` (62% weight on the incoming detection, 38% on the previous position). This reduces jitter from frame-to-frame detection noise.

---

## Feature Extraction

Features are computed per-track over a sliding 5-second window of the most recent observations. All fields are frozen dataclass members on `BehaviorFeatures`.

| Feature | Description |
|---|---|
| `mean_speed_px_s` | Total path distance divided by window duration (px/s) |
| `recent_speed_px_s` | Displacement between last two observations divided by elapsed time |
| `position_variance_px2` | Mean squared deviation of center points from window mean (px²) |
| `dwell_time_s` | Seconds the subject has remained within a 30px radius of their current position |
| `recent_vertical_delta_px` | Smoothed downward center displacement; averaged over last two frame-to-frame deltas to reduce single-frame jitter |
| `vertical_speed_px_s` | Signed vertical velocity between last two observations |
| `bbox_height_change_ratio` | Absolute bbox height change between last two frames, normalized by previous height |
| `direction_changes` | Count of direction reversals in the window (cosine < −0.2 between consecutive motion vectors) |
| `bbox_aspect_ratio` | Current bbox height/width. Standing person: 1.6–3.0. Fallen/collapsed: < 1.0 |
| `baseline_aspect_ratio` | Mean aspect ratio of the first 6 confirmed observations — the subject's upright standing baseline |

---

## Event Scoring

`EventScorer` applies threshold comparisons to produce a list of `BehaviorEvent` objects. Events have a cooldown of 2.5 seconds per (track, event_type) pair to prevent repeated firing.

**Event types and trigger conditions:**

| Event Type | Severity | Trigger |
|---|---|---|
| Movement anomaly | review_needed | `dwell_time_s >= 12.0s` (1.5× threshold) |
| Slow walking | normal | `mean_speed <= 18 px/s` AND `duration >= 2.0s` AND sufficient confidence |
| Postural Transition | medium | Deceleration pattern: `mean_speed >= 25.2 px/s` AND `recent_speed <= 9.9 px/s` AND `variance >= 270 px²`, not fall-like |
| Abrupt trajectory change | review_needed | `position_variance >= 2520 px²` (2.8× base threshold), not strong risk |
| Fall-like motion event | high | Any of: (a) motion-based: `vertical_delta >= 28px` AND `height_change >= 0.28` AND `variance >= 1125 px²`; or (b) posture-based: see below |

**Posture collapse detection** (`_posture_collapse()`): fires when `bbox_aspect_ratio < 1.2` AND `baseline_aspect_ratio >= 1.6` AND `drop >= 0.6` AND `variance >= 225 px²`. Captures subjects who have transitioned from upright to horizontal without requiring rapid per-frame motion signals — catches falls where the detector first sees the person already on the ground.

**Strong mobility risk** (`_strong_mobility_risk()`): gates the high-severity variance-based path. Requires one of: abrupt vertical shift + scale change together, sudden stop after fast motion, repeated direction changes with high variance, or posture collapse.

**Track qualification gates** (applied before scoring):
- `is_confirmed == True` (3+ consecutive hits)
- `duration_s >= 1.0s`
- Minimum 10 observations

---

## Overlay Labels

The annotated video draws per-subject overlays on every output frame. Overlay state is computed in `_risk_tone()` independently of the event scorer — it reflects instantaneous per-frame features rather than the cooldown-gated event log.

| Overlay Status | Color (BGR) | Label |
|---|---|---|
| `high` | Red `(45, 55, 220)` | High Mobility Risk Indicator |
| `medium` | Amber `(30, 190, 235)` | Postural Transition Detected |
| `review_needed` | Amber `(36, 166, 220)` | Movement Under Review |
| `insufficient_evidence` | Gray-blue `(155, 126, 92)` | Insufficient Evidence |
| `low` | Green `(75, 185, 95)` | Stable Gait |

**Risk tone logic (priority order):**
1. Recent event cache: a high/review event within the last 3 seconds elevates tone
2. Near frame boundary AND confidence < 0.38 → review_needed
3. Not confirmed AND confidence < 0.40 → insufficient_evidence
4. Posture collapse (same criteria as scorer) → high
5. Fall-like motion (vertical delta + height change + variance) → high
6. Postural transition (deceleration from walking) → medium
7. Dwell time >= 10s → medium; dwell >= 8s → review_needed
8. Default → low (green / Stable Gait)

**Secondary state label** (shown under the primary label):
`acquiring` | `fallen` | `stopped` | `slow` | `walking`

The `fallen` state fires from the same posture collapse geometry as the risk tone, so "Stable Gait / fallen" is not possible — posture collapse forces the tone to `high` before the state is read.

**Label format:** `#<track_id>  <status_label>` / `conf <value>  |  <state>`

**Label box fill:** semi-transparent (78% opacity) via OpenCV frame blend. Up to 5 labeled boxes per frame; additional subjects get a compact borderline-only box with track ID.

---

## Annotated Video Output

Frames are written to a temporary `mp4v`-encoded file by OpenCV, then transcoded by ffmpeg:

```
ffmpeg -y -loglevel error \
  -i <raw.mp4> \
  -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" \
  -vcodec libx264 \
  -pix_fmt yuv420p \
  -movflags +faststart \
  <output.mp4>
```

The `yuv420p` pixel format and `+faststart` flag are required for browser autoplay and seeking. The raw intermediate file is deleted after successful transcode. If ffmpeg is not installed, the API returns HTTP 503.

---

## Backend

### Stack

- Python 3.11+
- FastAPI 0.110+ with Uvicorn
- OpenCV 4.9+ (`opencv-python`)
- Ultralytics 8.4.0+ (YOLO26n)
- NumPy 1.26+
- python-multipart (upload support)

### Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

ffmpeg is required for annotated video output:

```bash
brew install ffmpeg        # macOS
apt install ffmpeg         # Debian/Ubuntu
```

### Model Weights

The detector expects `yolo26n.pt` in the `backend/` directory. It auto-downloads on first use if missing:

```
https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt
```

Override the path or use a different `.pt` file:

```bash
export STABILITYNET_DETECTOR_MODEL=/path/to/weights.pt
```

Verify the model loads correctly:

```bash
python smoke_test.py
```

### Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

### CLI

Analyze a video directly without starting the API:

```bash
python -m app.cli analyze \
  --video path/to/video.mp4 \
  --output outputs/result.json \
  --annotated-video outputs/annotated.mp4
```

Use a different detector model:

```bash
python -m app.cli analyze \
  --video path/to/video.mp4 \
  --output outputs/result.json \
  --detector-model yolo26s.pt
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `STABILITYNET_DETECTOR_MODEL` | `yolo26n.pt` | Path to `.pt` weights file, relative to `backend/` |
| `STABILITYNET_DETECTOR_DEVICE` | `cpu` | PyTorch device: `cpu`, `mps`, `cuda`, `cuda:0`, `auto` |
| `STABILITYNET_ANALYSIS_WIDTH` | `640` | Max frame width for inference (px) |
| `STABILITYNET_ANALYSIS_TARGET_FPS` | `22.0` | Target analysis frame rate (controls stride) |
| `STABILITYNET_ANALYSIS_FRAME_STRIDE` | `0` (auto) | Override analysis stride directly |
| `STABILITYNET_DETECTION_CONF_THRESHOLD` | `0.35` | Minimum detection confidence |
| `STABILITYNET_ANNOTATED_OUTPUT_MAX_WIDTH` | `1280` | Max width of annotated output video |
| `STABILITYNET_MAX_RENDERED_LABELS` | `5` | Max labeled boxes drawn per frame |
| `STABILITYNET_DISPLAY_EVENT_LIMIT` | `12` | Max events returned in API summary |
| `ALLOWED_ORIGINS` | `localhost:3000,3001` | Comma-separated CORS origins |

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Detector model status, configured path, auto-download availability |
| `POST` | `/analyses` | Run pipeline on a local sample path; returns full analysis record |
| `POST` | `/analyses/upload` | Upload an MP4 file; runs pipeline synchronously; returns full analysis record |
| `GET` | `/analyses/{id}` | Retrieve a saved analysis record by UUID |
| `GET` | `/analyses/{id}/video` | Stream the uploaded source MP4 for the given analysis |
| `GET` | `/outputs/{filename}` | Static file serve for annotated output videos |

Analysis records are stored as JSON files under `backend/outputs/analyses/`. Uploaded source videos are stored under `backend/outputs/uploads/`. Annotated output videos are stored under `backend/outputs/videos/`.

**Analysis record structure (key fields):**

```json
{
  "analysis_id": "<uuid>",
  "status": "completed",
  "analysis_version": "phase-1g",
  "frames_processed": 412,
  "frames_analyzed": 189,
  "raw_track_count": 4,
  "qualified_subject_count": 2,
  "raw_event_count": 7,
  "mobility_event_count": 3,
  "source_video_fps": 25.0,
  "effective_analysis_fps": 22.0,
  "cpu_analysis_throughput_fps": 16.6,
  "scene_reliability": "good",
  "annotated_video_url": "/outputs/videos/<file>.mp4",
  "tracks": [...],
  "events": [...],
  "summary": {...}
}
```

### Tests

```bash
python -m unittest discover -s tests
```

26 tests covering: feature extraction math, event scoring thresholds, tracker IoU matching and track expiry, pipeline policy (qualification, event merge, scene reliability), annotated video ffmpeg command shape, CLI argument parsing, and API integration with a fake pipeline runner.

---

## Frontend

### Stack

- Next.js 16 / React 19 / TypeScript 6
- No component library — all styling in `globals.css`
- No test suite — `typecheck` and `eslint` are the only checks

### Setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

### Architecture

All API traffic goes through Next.js route handlers in `src/app/api/stabilitynet/`. The browser never talks directly to the FastAPI backend. This eliminates CORS issues and keeps the backend URL configurable server-side.

| Route Handler | Proxies To |
|---|---|
| `analyses/route.ts` | `POST /analyses` |
| `analyses/upload/route.ts` | `POST /analyses/upload` |
| `analyses/[analysisId]/route.ts` | `GET /analyses/{id}` |
| `analyses/[analysisId]/video/route.ts` | `GET /analyses/{id}/video` (passes `Range`/`If-Range` for seeking) |
| `health/route.ts` | `GET /health` |
| `outputs/[filename]/route.ts` | `GET /outputs/{filename}` (range-aware for video streaming) |

The video proxy routes forward `Range` and `If-Range` headers verbatim. Removing these headers breaks Safari and Chrome video seeking.

### Backend URL

```bash
STABILITYNET_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

Defaults to `http://127.0.0.1:8000`.

### Validation

```bash
npm run typecheck
npm run lint
npm run build
```

---

## Output File Locations

```
backend/
  outputs/
    analyses/       JSON analysis records (one file per UUID)
    uploads/        Uploaded source MP4s
    videos/         Annotated H.264 output videos
  samples/          Sample MP4s for local-path analysis (not committed)
```

Sample videos referenced by the UI are placed in `backend/samples/`. Thumbnails for the sample picker are placed in `frontend/public/samples/thumbnails/` and are git-ignored.

---

## FPS Metrics

The analysis record exposes several FPS values that measure different things:

| Field | What It Measures |
|---|---|
| `source_video_fps` | Native frame rate of the input video file |
| `effective_analysis_fps` | Actual rate at which detection + tracking ran (after stride) |
| `cpu_analysis_throughput_fps` | Backend frames-per-second during the full pipeline loop |
| `end_to_end_processing_fps` | Total frames divided by wall-clock time including ffmpeg transcode |
| `playback_fps` | Annotated output video playback rate (matches source FPS) |

These are separated so source frame rate is not misread as measured processing throughput.

---

## Verify Annotated Output Codec

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,pix_fmt,codec_tag_string,width,height \
  -of default=noprint_wrappers=1 \
  backend/outputs/videos/<file>.mp4
```

Expected output:

```
codec_name=h264
codec_tag_string=avc1
pix_fmt=yuv420p
```

---

## Key Thresholds (all configurable via `BehaviorConfig`)

| Parameter | Default | Effect |
|---|---|---|
| `dwell_radius_px` | 30 px | Radius within which a stationary subject accumulates dwell time |
| `dwell_time_threshold_s` | 8.0 s | Dwell time required to trigger movement anomaly events |
| `slow_speed_threshold_px_s` | 18.0 px/s | Below this = slow walking event; used in postural transition thresholds |
| `unstable_variance_threshold_px2` | 900 px² | Base multiplier for variance-based scoring and overlay thresholds |
| `feature_window_s` | 5.0 s | Sliding window over which speed and variance are computed |
| `min_track_duration_s` | 1.0 s | Tracks shorter than this produce no events |
| `min_event_confidence` | 0.35 | Minimum detection confidence for event scoring |
| `min_track_frames` | 10 | Minimum observations before scoring is allowed |
| `event_cooldown_s` | 2.5 s | Minimum time between repeated events of the same type per track |

---

## Language Policy

All event labels and UI copy use **"mobility risk indicator"** and **"fall-like motion event"**. The strings "fall detected" and "diagnosis" do not appear anywhere in the codebase. The frontend sidebar displays "Not a medical device."
