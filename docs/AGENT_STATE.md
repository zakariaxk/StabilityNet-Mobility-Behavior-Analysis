# Agent State

## Current Phase

Phase 2: minimal synchronous API over the offline backend pipeline.

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

- Run the full pipeline against a real uploaded MP4 and inspect API/UI output
  before adding Redis or PostgreSQL.
