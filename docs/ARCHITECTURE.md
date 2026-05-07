# Architecture

StabilityNet models human mobility behavior from video using temporal analysis.
The first implementation is an offline backend pipeline.

## Phase 1 Flow

```text
video file
  -> OpenCV frame reader
  -> YOLOv8n person detector
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

## Module Boundaries

- `app.pipeline`: orchestration, frame ingestion, and result writing.
- `app.vision`: detector and tracker implementations.
- `app.schemas`: stable data contracts between pipeline stages.
- `app.utils`: small math and geometry helpers shared by pipeline stages.
