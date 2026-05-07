# Lessons

## Implementation Notes

- Empty architecture docs create ambiguity for agents and contributors. Keep
  phase scope, decisions, and current state updated as implementation moves.
- Pixel-based motion metrics are useful for Phase 1 but should not be presented
  as real-world gait speed without camera calibration.
- Keep command-line analysis functional as each pipeline layer lands. This makes
  later detector and tracker integration easier to validate.
