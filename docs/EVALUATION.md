# Evaluation

Phase 1 evaluation is focused on pipeline correctness, not clinical validity.

## Initial Checks

- Feature extraction produces expected values on synthetic tracks.
- Event scoring explains which thresholds were crossed.
- A local sample video produces detections, tracks, features, and JSON output.
- Pixel-based features are checked separately from detector accuracy so behavior
  math can be validated without video fixtures.
- Unit tests run without OpenCV or Ultralytics so core behavior logic can be
  validated in minimal environments.

## Event-Level Metrics

`app.evaluation.metrics.evaluate_events()` provides a deterministic, local
benchmark seam for labeled clips. Labels and predictions are matched one-to-one
by event type, subject track ID, and nearest timestamp within a configurable
tolerance. It reports:

- event precision, recall, and F1;
- false alarms per minute;
- mean absolute event timing error; and
- raw true-positive, false-positive, and false-negative counts.

These are engineering evaluation metrics, not evidence of clinical validity.
Use held-out clips and report the temporal tolerance with every result. An empty
clip with no predictions is treated as a correct negative; datasets should also
report how many positive and negative clips they contain so this convention is
not misleading.

The metric implementation is covered by synthetic tests and intentionally has
no OpenCV, model, cloud, or account dependency. A future manifest runner can
aggregate these per-clip results once timestamp labels exist.

## Deferred

- Real-world gait speed validation.
- Clinical mobility-risk correlation validation.
- Camera calibration benchmarks.
- Multi-camera consistency.
- Threshold calibration on a labeled, held-out dataset.
- Confidence intervals and stratification by FPS, resolution, occlusion, and
  camera motion.
