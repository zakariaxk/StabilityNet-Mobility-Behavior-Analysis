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
- Local file paths are useful for backend debugging but poor user experience.
  The review UI should make upload-and-review the primary workflow.
- Tested policy helpers are not protection if the production orchestration
  bypasses them. Keep a pure finalization seam and test the values returned to
  API clients.
- Persist analysis JSON with a same-directory temporary file and atomic replace;
  direct writes can turn a recoverable interruption into a corrupt record.
- Unknown or uncertain severity values must fail toward review, never toward a
  reassuring green presentation.
- Do not retune vision heuristics from demo impressions alone. Add labeled event
  metrics and invariance tests first, then measure changes on held-out clips.
