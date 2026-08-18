# Agent State

## Current Phase

Phase 3 (revised): background job execution over the offline pipeline, with a
labelled evaluation seam. Redis and PostgreSQL remain deferred — a
single-worker thread pool plus the JSON records already on disk solves the
blocking-request problem without them. See docs/FINISHING_PLAN.md.

## Completed

- Repository assessment.
- Phase 1 implementation plan.
- Backend package scaffold.
- OpenCV frame ingestion and JSON probe output.
- YOLO26n person detector boundary and Phase 1C detection output.
- SORT-style tracking with stable track IDs and JSON track summaries.
- Temporal feature extraction for dwell time, pixel speed, and position variance.
- Explainable event scoring for prolonged dwell, low mobility speed, and high
  position variance.
- Unit tests for feature extraction, event scoring, and SORT-style tracking.
- Local FastAPI analysis submission and retrieval endpoints.
- API summaries for frontend-friendly frame, track, and event counts.
- Local Next.js development CORS support.
- Direct MP4 upload support with saved video playback in the review UI.

## Next

- Split the 1,700-line frontend page component (S8).
- Prune the outputs directory and commit real sample thumbnails (S10).
- Threshold sensitivity sweep against a larger labelled set (SF1).
