# AGENTS.md — StabilityNet Codebase Context

## What This Project Does

StabilityNet analyzes uploaded MP4 videos to detect human mobility patterns that may require clinical review, using YOLO26n person detection, SORT-style tracking, and heuristic event scoring. It exposes a Next.js frontend and a FastAPI backend, running fully locally — it is a research prototype, not a medical device.

---

## Folder / File Structure

```
StabilityNet/
├── AGENTS.md                         ← (this file) AI session context
├── MEMORY.md                         ← Decisions, lessons, open questions
├── MANUAL_ACTIONS.md                 ← Step-by-step human setup checklist
├── README.md                         ← Project overview and FPS metric definitions
├── LICENSE
├── .github/
│   └── copilot-instructions.md       ← Architecture and conventions reference for Copilot/Codex
├── docs/
│   ├── ARCHITECTURE.md               ← Phase flow diagram, module boundaries, signal types
│   ├── DECISIONS.md                  ← Architecture decision records (ADR-001 through ADR-008)
│   ├── ROADMAP.md                    ← Phase 1–5 goals
│   ├── AGENT_INSTRUCTIONS.md         ← Rules for AI agents working in this repo
│   ├── AGENT_STATE.md                ← Completed phases and what comes next
│   ├── EVALUATION.md                 ← What Phase 1 evaluation covers (not clinical)
│   ├── LESSONS.md                    ← Implementation lessons learned
│   └── PROJECT_OVERVIEW.md           ← One-paragraph project summary
├── backend/
│   ├── README.md                     ← Backend setup, API usage, annotated output verification
│   ├── .env.example                  ← ALLOWED_ORIGINS, STABILITYNET_DETECTOR_MODEL/DEVICE
│   ├── app/
│   │   ├── __init__.py               ← Package version (0.1.0)
│   │   ├── main.py                   ← FastAPI app factory, CORS, static /outputs mount
│   │   ├── cli.py                    ← CLI entrypoint: `stabilitynet analyze --video --output`
│   │   ├── config.py                 ← All config dataclasses + env-var overrides
│   │   ├── api/
│   │   │   ├── routes.py             ← FastAPI routes: /health, /analyses, /analyses/upload, /analyses/{id}, /analyses/{id}/video
│   │   │   ├── analysis_service.py   ← Service layer: runs pipeline, saves records, normalizes results
│   │   │   └── schemas.py            ← Pydantic models: AnalysisCreateRequest, AnalysisRecord
│   │   ├── behavior/
│   │   │   ├── events.py             ← BehaviorEvent dataclass (immutable, serializable)
│   │   │   ├── features.py           ← BehaviorFeatures dataclass + extract_features() function
│   │   │   ├── scoring.py            ← EventScorer: heuristic threshold scoring → list[BehaviorEvent]
│   │   │   └── track_state.py        ← TrackPoint, TrackHistory, TrackStore (temporal accumulation)
│   │   ├── pipeline/
│   │   │   ├── annotated_video.py    ← AnnotatedVideoWriter: draws overlays, calls ffmpeg for H.264
│   │   │   ├── frame_reader.py       ← VideoFrameReader: OpenCV frame ingestion, metadata
│   │   │   ├── result_writer.py      ← write_json(): atomic JSON output
│   │   │   └── video_pipeline.py     ← analyze_video(): main orchestration loop
│   │   ├── schemas/
│   │   │   ├── detection.py          ← BoundingBox, Detection dataclasses
│   │   │   ├── tracking.py           ← TrackObservation dataclass
│   │   │   └── behavior.py           ← Re-exports BehaviorFeatures
│   │   ├── utils/
│   │   │   ├── __init__.py
│   │   │   └── geometry.py           ← bbox_iou(): IoU for tracker matching
│   │   └── vision/
│   │       ├── detector.py           ← PersonDetector Protocol, error classes
│   │       ├── sort_tracker.py       ← SortTracker: greedy IoU + center-distance matching
│   │       ├── tracker.py            ← MultiObjectTracker Protocol
│   │       └── yolo_detector.py      ← YOLOPersonDetector: Ultralytics YOLO26n wrapper + model cache
│   ├── tests/
│   │   ├── test_api.py               ← FastAPI integration tests (fake runner, no real video)
│   │   ├── test_annotated_video.py   ← ffmpeg path tests (patched subprocess)
│   │   ├── test_cli.py               ← CLI arg parsing and dispatcher tests
│   │   ├── test_features.py          ← Feature extraction math tests
│   │   ├── test_pipeline_policy.py   ← Track qualification, event merge, scene reliability tests
│   │   ├── test_scoring.py           ← EventScorer threshold tests
│   │   ├── test_tracker.py           ← SortTracker IoU matching and track expiry tests
│   │   └── test_yolo_detector.py     ← YOLOPersonDetector with fake YOLO model
│   ├── samples/
│   │   └── README.md                 ← Expected sample MP4 filenames (not committed)
│   ├── smoke_test.py                 ← Verifies YOLO26n loads and runs a tiny inference pass
│   └── test_video_upload.py          ← Stdlib-only curl helper for manual upload testing
├── frontend/
│   ├── package.json                  ← Next.js 16, React 19, TypeScript 6; scripts: dev/build/lint/typecheck
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx            ← Root layout with metadata
│   │   │   ├── page.tsx              ← Full single-page UI (upload, samples, summary, video, tracks, events)
│   │   │   ├── globals.css           ← All styling
│   │   │   └── api/stabilitynet/
│   │   │       ├── analyses/route.ts           ← POST proxy → /analyses
│   │   │       ├── analyses/upload/route.ts    ← POST proxy → /analyses/upload (form data)
│   │   │       ├── analyses/[analysisId]/route.ts     ← GET proxy → /analyses/{id}
│   │   │       ├── analyses/[analysisId]/video/route.ts ← GET range-aware proxy → /analyses/{id}/video
│   │   │       ├── health/route.ts             ← GET proxy → /health
│   │   │       └── outputs/[filename]/route.ts ← GET range-aware proxy → /outputs/{filename}
│   │   └── lib/
│   │       ├── backendProxy.ts       ← proxyBackendJson/FormData/VideoResponse: fetch wrappers to FastAPI
│   │       ├── sampleVideos.ts       ← SAMPLE_VIDEOS list and thumbnail paths
│   │       └── stabilityNetApi.ts    ← Type definitions + fetch helpers; analysisVideoUrl() fallback chain
│   └── public/
│       └── samples/thumbnails/       ← Sample thumbnail images (JPGs, not committed to git)
└── scripts/
    └── generate_sample_thumbnails.sh ← Shell helper (generates thumbnails from sample MP4s)
```

---

## Most Important Files (Read These First)

| File | Why |
|---|---|
| `backend/app/pipeline/video_pipeline.py` | Main analysis orchestration loop — detection, tracking, feature extraction, scoring, annotation all wired here |
| `backend/app/behavior/scoring.py` | Where all severity decisions are made: thresholds, event types, fall-like motion detection |
| `backend/app/pipeline/annotated_video.py` | Where overlay labels, colors, and `_status_label()` are rendered — this drives what users *see* |
| `backend/app/behavior/features.py` | The six key features extracted per track (speed, variance, dwell, vertical delta, height change, direction changes) |
| `backend/app/config.py` | All default numeric thresholds; changing these changes every scoring decision downstream |
| `backend/app/vision/sort_tracker.py` | The tracker — IoU + center distance matching, track lifecycle |
| `frontend/src/app/page.tsx` | Entire frontend UI — single large component file |
| `frontend/src/lib/stabilityNetApi.ts` | Type definitions and `analysisVideoUrl()` fallback chain |

---

## Key Thresholds (from `config.py`)

| Name | Default | Used In |
|---|---|---|
| `dwell_radius_px` | 30.0 px | Dwell time calculation |
| `dwell_time_threshold_s` | 8.0 s | Movement anomaly event, risk_tone |
| `slow_speed_threshold_px_s` | 18.0 px/s | Slow walking event, motion state |
| `unstable_variance_threshold_px2` | 900.0 px² | Position variance event, risk_tone, motion state |
| `min_track_duration_s` | 1.0 s | Gate for scoring |
| `min_event_confidence` | 0.35 | Gate for scoring low-confidence events |
| `min_track_frames` | 10 | Gate for track qualification |
| `TRACK_IOU_THRESHOLD` | 0.3 | Tracker match acceptance |
| `TRACK_MIN_HITS` | 3 | Frames before a track is "confirmed" |
| `TRACK_MAX_AGE` | 20 frames | Frames before expired track is dropped |

---

## What Must Never Be Changed

1. **`_finalize_output()` in `annotated_video.py`** — The ffmpeg command uses `-vcodec libx264 -pix_fmt yuv420p -movflags +faststart`. These flags are what make the output browser-playable. A test (`test_ffmpeg_transcode_uses_h264_yuv420p`) enforces this. Do not touch.
2. **`VideoFrameReader._read_fps()`** — FPS comes from the video's own metadata; fallback only when metadata is invalid. Never hardcode or fake FPS.
3. **`backendProxy.ts` → `proxyBackendVideoResponse()`** — Passes `Range` and `If-Range` headers to backend for browser streaming. Remove these and Safari/Chrome video seeking breaks.
4. **`_resolve_sample_video_path()` in `analysis_service.py`** — Blocks absolute paths and `..` traversal. This is a path traversal security gate.
5. **Event language** — Never use "fall detected" or "diagnosis". Use "fall-like motion event" and "mobility risk indicator". This is enforced through all label text in `_status_label()` and `_default_event_description()`.
6. **`analysis_version`** field in pipeline output — Currently `"phase-1g"`. Clients rely on this to distinguish payload versions.

---

## Current Known Bugs / Issues

1. **`_track_motion_state()` in `video_pipeline.py` uses a different variance threshold (2200 px²)** than `_risk_tone()` in `annotated_video.py` (900 × 2.8 = 2520 px²) — the two are inconsistent and can produce different labels for the same subject. (The 2.8x multiplier in `_risk_tone()` was raised from 1.7x to fix green suppression.)

2. **No test covers the `_risk_tone()` or `_status_label()` logic** — All annotated video scoring is untested (only ffmpeg path coverage exists in `test_annotated_video.py`).

_Previously fixed:_
- ~~"Tracking Instability" on stable subjects~~ — fixed: `_status_label("medium")` → "Postural Transition Detected", `_status_label("review_needed")` → "Movement Under Review"
- ~~Green overlay threshold too high~~ — fixed: variance threshold raised from 1.7× to 2.8× (1530 → 2520 px²) in `_risk_tone()`
- ~~"Insufficient Evidence" fires too broadly~~ — fixed: gate changed from `observations < 3 and confidence < 0.45` to `not is_confirmed and confidence < 0.40`
- ~~Assisted-walk-sit mislabeled~~ — fixed: `_risk_tone()` now detects deceleration-from-walking pattern → "medium" → "Postural Transition Detected"

---

## Demo Goal

Four sample clips, run through the UI at `http://localhost:3000`:

| Sample | Expected behavior |
|---|---|
| `office-hallway-walk.mp4` | Stable green overlays, "Stable" label, no amber/red |
| `assisted-walk-sit.mp4` | Amber overlay during sit-down transition, label "Postural Transition Detected" |
| `two-person-approach.mp4` | Two stable tracked subjects, green overlays |
| `warehouse-fall.mp4` | Red overlay + "High Mobility Risk Indicator" + "Fall-like motion event" in events timeline |

---

## Coding Patterns and Conventions

- **Python style**: `from __future__ import annotations` on all files; frozen dataclasses for data contracts; Protocol types for interfaces; `mypy`-compatible type hints throughout.
- **Tests**: `unittest.TestCase` style (no pytest style), fake/stub runners via dependency injection, no real video or real model weights required in unit tests.
- **Backend test runner**: `python3 -m unittest discover -s tests`
- **No pytest marks**: tests use plain `setUp()`/helper functions.
- **Frontend**: Single-page React with no component library; all CSS in `globals.css`; all utility types and fetch wrappers in `lib/`; API calls never go directly to backend — always through Next.js route handlers.
- **Event severity system** (backend → frontend):
  - `"normal"` → green / "Stable Gait"
  - `"review_needed"` → amber / "Movement Under Review"
  - `"medium"` → amber / "Postural Transition Detected"
  - `"insufficient_evidence"` → gray-blue / "Insufficient Evidence"
  - `"high"` → red / "High Mobility Risk Indicator"
- **Overlay colors** (BGR in OpenCV): red `(45, 55, 220)`, amber `(30, 190, 235)`, gray-blue `(155, 126, 92)`, green `(75, 185, 95)`.
- **Annotated video pipeline**: raw `.mp4v` → ffmpeg → H.264/yuv420p. The raw file is always deleted after transcoding.
- **Model caching**: `_MODEL_CACHE` dict in `yolo_detector.py` prevents reloading the same `.pt` file across requests within the same process.
- **`analysis_version`**: currently `"phase-1g"` in `video_pipeline.py:260`.

---

## Non-Obvious Gotchas

1. **`SortTracker` uses both IoU and center distance** — `score = max(iou_score, center_score)`. A detection that has drifted in bbox size but stayed close in center can still match via center score alone. This matters for tracking someone transitioning from standing to sitting.

2. **`position_variance_px2` is computed over a sliding `feature_window_s = 5.0s` window**, not the full track. A subject who moves differently in the last 5s than earlier will have a variance that doesn't reflect the full history.

3. **`_recent_vertical_delta_px` is signed**: positive means the person moved downward in frame. The scoring code checks `>= 28.0` (raw magnitude) which means downward movement triggers it, not upward.

4. **Frame stride**: at high source FPS, `analysis_frame_stride` can be > 1. Frames skipped between analyses carry the **previous** observation's bbox (frozen), not an interpolated position. Features on the "off" frames are the features from the last analyzed frame.

5. **The `analysis_version` field in the JSON output is `"phase-1g"`** — this string is not bumped consistently; if you add a breaking pipeline change, bump it.

6. **`_select_label_track_ids()` limits drawn labels to `MAX_RENDERED_LABELS_PER_FRAME` (default 5)** — subjects beyond this count still get a compact box but no text label. The HUD always shows counts.

7. **`_bbox_near_boundary()` appears three times** in slightly different forms: `annotated_video.py`, `video_pipeline.py`, and `scoring.py` each compute their own boundary check with slightly different margin values (4%, 4.5%, 4%).

8. **`analysis_service.py` normalizes event severity** via `_severity_value()` — unknown severity strings become `"low"`, not `"review_needed"`. This is different from `_event_severity()` in `video_pipeline.py` which defaults to `"review_needed"`.

9. **The frontend `analysisVideoUrl()` has a 6-level fallback chain** — if the backend adds a new field name for the video URL, add it to the chain in `stabilityNetApi.ts` to maintain compatibility.

10. **No frontend tests exist** — `package.json` has no test script. `typecheck` and `lint` are the only CI checks.

11. **CORS config**: wildcard `"*"` origin disables `allow_credentials` automatically (FastAPI behavior). The default allowed origins are hardcoded `localhost:3000/3001`. Backend URL is `STABILITYNET_API_BASE_URL` env var in frontend (defaults to `http://127.0.0.1:8000`).
