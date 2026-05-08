# Decisions

## ADR-001: Start Offline Before API

The first backend phase analyzes local video files from a CLI. This keeps the
core detection, tracking, and behavior logic testable before adding API,
database, queue, or frontend layers.

## ADR-002: Use YOLOv8n For Initial Person Detection

YOLOv8n gives a small, practical detector for early iteration. The detector is
wrapped behind a narrow module boundary so a later model can replace it without
rewriting the pipeline.

## ADR-003: Use SORT-Style Tracking First

SORT-style tracking is lightweight and enough to create persistent identities
for Phase 1 behavior features. More robust re-identification is deferred until
occlusion and identity-switch problems are measured.

The first tracker uses greedy IoU association with SORT-style track lifecycle
settings. A full Kalman filter and Hungarian assignment can replace this module
later if identity switches become a measured problem.

## ADR-004: Use Heuristic Event Scoring Initially

Phase 1 event scoring uses transparent thresholds for dwell time, speed, and
position variance. Learned anomaly models are deferred until the project has
real outputs and evaluation data.

The pipeline emits the first occurrence of each event type per track to keep
offline JSON output readable. Richer event lifecycle semantics are deferred.

## ADR-005: Keep Phase 2 API Synchronous And Local

The first API accepts a local video path, runs the existing pipeline
synchronously, and stores JSON records on disk. Upload handling, Redis queues,
PostgreSQL persistence, and frontend integration are deferred until real local
video output has been inspected.

## ADR-006: Add API Summary Fields Before Persistence

API records include compact frame, track, and event counts so UI clients do not
need to infer basic totals from the full nested pipeline output. This remains a
disk-backed Phase 2 contract and does not require Redis or PostgreSQL.

## ADR-007: Support Direct MP4 Upload Before Job Queues

The UI should not require users to type backend-local sample paths. Phase 2
accepts MP4 uploads, saves them under ignored local output storage, analyzes the
saved file synchronously, and exposes the uploaded video for playback. Redis and
PostgreSQL remain deferred until the synchronous upload path is validated with
real videos.

## ADR-008: Upgrade Default Detector To YOLO26n

Ultralytics YOLO26n replaces YOLOv8n as the default person detector because it
keeps the nano-size deployment profile while improving current speed and
accuracy expectations. The existing detector wrapper and JSON output contract
stay unchanged, and the CLI exposes `--detector-model` so local runs can compare
other YOLO26 variants or custom `.pt` weights without changing code.
