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

## ADR-009: Make Reliability Policy Part Of Production Output

Track qualification, scene reliability, and display-event suppression are one
production post-processing step. Raw tracks and raw event counts remain
available for debugging, while `qualified_tracks`, presented events, and
reliability fields reflect the review policy. This prevents short or weak tracks
from being presented as qualified subjects without hiding the underlying data.

## ADR-010: Evaluate Events Before Retuning Heuristics

StabilityNet uses a local event-level evaluation seam with one-to-one temporal
matching, precision, recall, F1, false alarms per minute, and timing error. Major
tracker or scoring changes should be justified against labeled held-out clips
and synthetic invariance tests rather than tuned only to the four demo videos.
These metrics evaluate prototype behavior and do not establish clinical validity.


## ADR-011: Background Jobs Via A Thread Pool, Not Redis

Analysis ran inside the HTTP request, so an upload blocked for the full
pipeline — inference plus an ffmpeg transcode — with no progress and no
cancel. ADR-005 accepted that while the pipeline was stabilising.

The fix is a module-level `ThreadPoolExecutor(max_workers=1)` and a `progress`
object persisted onto the existing JSON record. Submission returns `202`; the
client polls. No Redis, no Celery, no database.

One worker on purpose: analyses are CPU-bound, so concurrent workers make
every analysis slower and deliver no result sooner. Queueing is the honest
behaviour and it is what the API reports.

Consequence: mid-pipeline failures can no longer be HTTP status codes. They
are recorded on the record as `status: "failed"` with `message` and
`error_kind`. Pre-flight validation stays synchronous.

## ADR-012: The API Does Not Return The Per-Frame Trace

`result["frames"]` carries one entry per frame with every detection, track and
feature. Returning it made analysis responses reach several megabytes, which
the browser then parsed to reconstruct trajectories that `tracks[].trajectory`
already contained.

The response now omits `frames`, `tracks`, `qualified_tracks` and `events`
from the nested `result` object — all four are already top-level record
fields, and `tracks` was being serialised three times per response. The full
trace still goes to `outputs/analyses/<id>.result.json` and is served by
`GET /analyses/{id}/frames`.

Measured on `samples/warehouse-fall.mp4`: 1.6 MB trace on disk, 105 KB
response.

## ADR-013: Scene-Level Causes Are Reported Once, Not Per Subject

When camera motion is detected in a clip, per-track position variance has a
single shared explanation. Reporting `Abrupt trajectory change` per subject
turned one hand-held sequence into 19 independent-looking findings on
`assisted-walk-sit.mp4`.

Those rows now collapse to one entry carrying a count when camera motion was
detected in the same clip. The same aggregation applies to the two track-end
uncertainty types, which are per-track by nature.

Detection is unchanged — this is presentation only, and
`docs/EVALUATION_RESULTS.md` records that precision, recall, F1 and timing
error were identical before and after.
