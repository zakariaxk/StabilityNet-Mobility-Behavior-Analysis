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
