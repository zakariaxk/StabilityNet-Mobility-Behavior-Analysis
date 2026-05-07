# Lessons

## Implementation Notes

- Empty architecture docs create ambiguity for agents and contributors. Keep
  phase scope, decisions, and current state updated as implementation moves.
- Pixel-based motion metrics are useful for Phase 1 but should not be presented
  as real-world gait speed without camera calibration.
- Keep command-line analysis functional as each pipeline layer lands. This makes
  later detector and tracker integration easier to validate.
- Vision dependencies should fail with explicit setup guidance. Minimal local
  environments may not have OpenCV or Ultralytics installed yet.
- Early behavior events should explain the exact threshold signal they came
  from. This keeps results debuggable before any learned anomaly model exists.
- API work should wrap the pipeline, not absorb it. Keeping FastAPI thin
  preserves the CLI and makes later queue/database work easier to add.
- Browser-based clients need CORS even for local development. Support only local
  Next.js development origins for now.
