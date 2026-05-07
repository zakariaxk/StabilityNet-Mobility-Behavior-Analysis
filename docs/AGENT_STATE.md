# Agent State

## Current Phase

Phase 1: offline backend video detection pipeline.

## Completed

- Repository assessment.
- Phase 1 implementation plan.
- Backend package scaffold.
- OpenCV frame ingestion and JSON probe output.
- YOLOv8n person detector boundary and Phase 1C detection output.
- SORT-style tracking with stable track IDs and JSON track summaries.
- Temporal feature extraction for dwell time, pixel speed, and position variance.
- Explainable event scoring for prolonged dwell, low mobility speed, and high
  position variance.
- Unit tests for feature extraction, event scoring, and SORT-style tracking.

## Next

- Run the full pipeline against a real local video after installing backend
  dependencies.
