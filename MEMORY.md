# MEMORY.md — StabilityNet Running Log

_Updated: 2026-05-10_

---

## Decisions Made and Why

### ADR-001: CLI before API
Start with `app.cli` / offline pipeline before adding FastAPI. Keeps detection, tracking, and behavior logic testable without HTTP or upload machinery. Allows validating JSON output against real videos first.

### ADR-002: YOLOv8n → YOLO26n
Initially used YOLOv8n; upgraded to YOLO26n (Ultralytics v8.4.0) for better accuracy/speed at the same nano footprint. The weights auto-download from `https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt` if missing.

### ADR-003: Greedy IoU tracker first, Kalman deferred
SORT-style greedy IoU + center-distance matching is enough for Phase 1 single-camera, uncrowded scenes. Full Kalman filter and Hungarian assignment are deferred until identity-switch problems are actually measured in the demo clips.

### ADR-004: Heuristic scoring, not ML
Event scoring uses transparent numeric thresholds (dwell time, speed, variance). Learned anomaly models deferred until real output data and evaluation criteria exist.

### ADR-005: Synchronous FastAPI, no queues
Phase 2 runs the pipeline synchronously inside the API request. Redis queues and PostgreSQL persistence are deferred until the synchronous upload path is validated with real videos.

### ADR-006: Disk-backed records, no database
Analysis records stored as JSON files under `outputs/analyses/`. This keeps Phase 2 shippable without setting up PostgreSQL.

### ADR-007: Direct upload before job queues
UI uses `/analyses/upload` multipart form upload. No job ID polling — the HTTP response is the result. Queues deferred.

### ADR-008: YOLO26n as new default detector
`DEFAULT_DETECTOR_MODEL = "yolo26n.pt"`. CLI exposes `--detector-model` to compare other `.pt` files without code changes.

### Annotated video: ffmpeg H.264/yuv420p
The annotated output is written as raw `mp4v` by OpenCV, then transcoded via ffmpeg to H.264/yuv420p with `+faststart` for browser streaming. This is the only format browsers reliably autoplay. A test (`test_ffmpeg_transcode_uses_h264_yuv420p`) pins the exact codec flags.

### Frontend: all traffic through Next.js proxy
The frontend never hits the FastAPI backend directly — all calls go through Next.js route handlers in `src/app/api/stabilitynet/`. Video routes pass `Range`/`If-Range` headers for browser-native seeking. This avoids CORS and keeps the backend URL configurable server-side (`STABILITYNET_API_BASE_URL`).

### Language policy: indicators not diagnoses
All event labels, reasons, and UI copy use "mobility risk indicator" and "fall-like motion event". "Fall detected" and "diagnosis" are explicitly banned. The sidebar says "Not a medical device."

---

## Things That Were Tried and Failed / Rolled Back

_(Log failed experiments here as they happen.)_

- **Overly liberal "Tracking Instability" labeling** — FIXED (2026-05-10). `_status_label()` now maps "medium" → "Postural Transition Detected" and "review_needed" → "Movement Under Review". "Tracking Instability" no longer exists as an overlay label.

- **Tight variance thresholds causing green suppression** — FIXED (2026-05-10). `_risk_tone()` in `annotated_video.py` now uses 2.8× multiplier (2520 px²) instead of 1.7× (1530 px²) for the "review_needed" variance gate. Scoring.py `review_threshold` raised from 1.7× to 2.8× as well. Normal brisk walking (typically 800–2000 px² variance in 5s window) now stays green.

### Overlay label + scoring changes (2026-05-10)

**`annotated_video.py` — `_risk_tone()`:**
- Variance threshold for "review_needed" raised: 1.7× → 2.8× (1530 → 2520 px²)
- Added postural-transition detection: `mean_speed >= 1.4× slow_threshold AND recent_speed <= 0.55× slow_threshold AND variance >= 0.3× threshold` → "medium" → "Postural Transition Detected"
- "Insufficient Evidence" gate tightened: was `observations < 3 and confidence < 0.45`; now `not is_confirmed and confidence < 0.40`

**`annotated_video.py` — `_status_label()`:**
- "medium" → "Postural Transition Detected" (was "Tracking Instability")
- "review_needed" → "Movement Under Review" (was "Tracking Instability")
- "low" → "Stable Gait" (was "Stable")

**`scoring.py`:**
- `review_threshold` raised from 1.7× to 2.8× to match annotated_video.py
- Added `_postural_transition()` helper: detects deceleration from walking to near-stop
- Added "Postural Transition" event emission (severity="medium", score=0.55) before high/review block

**`features.py` — `_recent_vertical_delta()`:**
- Now averages last two frame-to-frame deltas (3 points) instead of using only the last 2 points. Reduces single-frame jitter noise while preserving genuine multi-frame falls (both deltas are large and same-sign).

**`tests/test_scoring.py`:**
- Updated `test_high_severity_requires_strong_motion_evidence`: brisk steady walking at 1600 px² variance now correctly produces `[]` (below new 2.8× threshold); previously expected `["Abrupt trajectory change"]`.

---

## Things That Are Intentionally This Way

- **`_bbox_near_boundary()` implemented three times** — each usage has slightly different margin ratios (4% in `scoring.py`, 4% in `video_pipeline.py`, 4.5% in `annotated_video.py`). This is not a refactoring opportunity yet because the three contexts have different needs; don't consolidate prematurely.

- **`annotated_video.py` does not draw raw detections** — the `_ = detections` line is intentional. Drawing detection boxes (pre-tracking) clutters the output; only tracked subject overlays are shown.

- **Track centers are capped at 24 history points** in `_append_track_center()` — this is a display-only ring buffer for the trajectory trail. The actual `TrackHistory.points` in `track_state.py` is unbounded (grows for the full video duration).

- **`is_confirmed` requires only 1 hit in `_TrackedObject`** (`hits >= 1`) — this is the low-level tracker's own `is_confirmed` property for its internal lifecycle. The `TrackObservation.is_confirmed` passed downstream uses `hits >= config.min_hits` (default 3). The two are different.

- **`_safe_uuid()` in `analysis_service.py`** — analysis IDs are validated as UUIDs on read. Any non-UUID string raises `AnalysisNotFoundError` with a 404, not 400. This is intentional to prevent path traversal via crafted analysis IDs.

- **Backend normalizes event severity on ingestion** — `_normalize_events()` in `analysis_service.py` applies `_severity_value()` which defaults unknown severities to `"low"`, while `video_pipeline.py`'s `_event_severity()` defaults to `"review_needed"`. This asymmetry is intentional: the pipeline is strict, the ingestion layer is lenient for external compatibility.

- **`analysis_version = "phase-1g"`** — this string tracks pipeline payload version. Bump it when the JSON output contract changes in a way that breaks existing consumers.

- **Frontend has no test suite** — confirmed gap; `package.json` has no test script. `typecheck` and `eslint` are the only checks.

---

## Open Questions

1. **When to bump `analysis_version`?** Currently `"phase-1g"`. No documented policy for what constitutes a breaking change.

2. **Postural transition detection**: The assisted-walk-sit scenario needs a specific behavioral fingerprint (large `recent_vertical_delta_px` + large `bbox_height_change_ratio` + decreasing speed, but NOT high position variance from chaotic motion). How should this be distinguished from a fall-like event programmatically?

3. **`_track_motion_state()` threshold inconsistency**: `video_pipeline.py` uses `variance >= 2200.0` for "review" state, but `annotated_video.py` uses `variance >= 900 * 1.7 = 1530.0`. These should be aligned — but which is the right threshold?

4. **`_recent_vertical_delta_px` uses only the last 2 points** — this makes it very noisy. Should it be smoothed over N recent frames?

5. **Track ID reuse**: After a track expires (`missed_frames > max_age_frames`), the next new detection gets the next monotonically increasing ID. IDs are never reused, so `_next_track_id` only grows. This is fine for short clips but could become large for long videos.

6. **Redis and PostgreSQL** are listed in the tech stack in `docs/AGENT_INSTRUCTIONS.md` but are not in the codebase at all. Phase 3 work.

7. **No sample thumbnails are committed** — `frontend/public/samples/thumbnails/*.jpg` are expected but gitignored. The UI gracefully falls back to a placeholder icon.

8. **Camera motion detection** (`_camera_motion_uncertainty_event()`) is implemented in `video_pipeline.py` but is not called anywhere in the current frame loop. It appears to be dead code.

9. **`_display_events()` and `_track_end_events()`** are implemented in `video_pipeline.py` but `analyze_video()` does not call them — these functions are only exercised via unit tests. The pipeline currently uses `_merge_nearby_events()` directly.

10. **`severityClass()` in frontend** (`page.tsx`) maps `"review_needed"` and `"insufficient_evidence"` to `"low"` (green badge) because neither contains the word "medium" or "high". This means amber events can appear green in the events table severity badge.
