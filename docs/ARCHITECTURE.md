# Architecture

StabilityNet models human mobility behavior from video using temporal analysis.
The first implementation is an offline backend pipeline.

## Phase 1 Flow

```text
video file
  -> OpenCV frame reader
  -> YOLO26n person detector
  -> SORT-style tracker
  -> per-track temporal state
  -> behavior feature extraction
  -> threshold event scoring
  -> JSON analysis output
```

## Core Signals

- Dwell time: how long a tracked person remains within a small spatial radius.
- Movement speed: pixel displacement per second until camera calibration exists.
- Position variance: center-point variance over a recent time window.

## Boundaries

The analysis pipeline must stay independent from FastAPI. API endpoints can call
the pipeline later, but they should not contain detection, tracking, or behavior
logic.

## Phase 2 API Flow

```text
POST /analyses/upload with MP4 file
  -> uploaded file saved under backend/outputs/uploads
  -> synchronous pipeline run
  -> JSON record written under backend/outputs/analyses
  -> analysis ID, compact summary, and video URL returned
  -> GET /analyses/{analysis_id} retrieves the saved record
  -> GET /analyses/{analysis_id}/video streams the uploaded MP4

POST /analyses with local video path
  -> synchronous pipeline run
  -> JSON record written under backend/outputs/analyses
  -> analysis ID and compact summary returned
  -> GET /analyses/{analysis_id} retrieves the saved record
```

## Module Boundaries

- `app.pipeline`: orchestration, frame ingestion, and result writing.
- `app.api`: FastAPI routes and local result-record service.
- `app.behavior`: track histories, temporal features, and event scoring.
- `app.vision`: detector and tracker implementations.
- `app.schemas`: stable data contracts between pipeline stages.
- `app.utils`: small math and geometry helpers shared by pipeline stages.

## Event Semantics

Events are heuristic mobility-pattern indicators based on configured thresholds.
They are not clinical diagnoses and should be reviewed in context.

## Metric Semantics

- `source_video_fps` / `source_fps`: native FPS of the uploaded/sample MP4.
- `effective_analysis_fps`: sampled analysis cadence when high-FPS inputs use frame stride.
- `cpu_analysis_throughput_fps`: CPU throughput across decode, detection, tracking, event scoring, and annotation.
- `end_to_end_processing_fps` / `processing_fps`: full pipeline throughput including H.264/yuv420p output writing.
- `raw_track_count`: internal tracker IDs before quality gates.
- `qualified_subject_count`: stable tracks eligible for UI subject summaries.
- `scene_reliability`: high, medium, or low reliability based on crowding, fragmentation, and camera-motion uncertainty.
- `playback_fps`: annotated output playback timing.

This separation prevents overstating model inference speed in demos or resume bullets.
