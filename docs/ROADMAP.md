# Roadmap

## Phase 1: Offline Video Pipeline

- Read local video files.
- Detect people with YOLO26n.
- Track people with SORT-style identities.
- Compute dwell time, movement speed, and position variance.
- Emit explainable instability events and JSON output.
- Add focused tests around feature extraction and scoring.

## Phase 2: Minimal API

- Add FastAPI endpoints for health, MP4 upload, video submission, and result retrieval.
- Keep processing synchronous until pipeline behavior is stable.

## Phase 3: Jobs And Persistence

- Add Redis-backed job state or queueing.
- Add PostgreSQL analysis records and event storage.

## Phase 4: Review UI

- Add a Next.js/TypeScript interface for uploading and viewing videos while
  reviewing tracks and events.

## Phase 5: Calibration And Robustness

- Add camera calibration, smoothing improvements, better occlusion handling, and
  richer evaluation datasets.
