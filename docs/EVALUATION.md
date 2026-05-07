# Evaluation

Phase 1 evaluation is focused on pipeline correctness, not clinical validity.

## Initial Checks

- Feature extraction produces expected values on synthetic tracks.
- Event scoring explains which thresholds were crossed.
- A local sample video produces detections, tracks, features, and JSON output.
- Pixel-based features are checked separately from detector accuracy so behavior
  math can be validated without video fixtures.

## Deferred

- Real-world gait speed validation.
- Clinical fall-risk validation.
- Camera calibration benchmarks.
- Multi-camera consistency.
