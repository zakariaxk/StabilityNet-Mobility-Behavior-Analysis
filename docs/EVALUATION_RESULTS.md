# Evaluation results

Produced by `backend/eval/run_eval.py` against the hand-labelled clips in
`backend/eval/labels/`. Re-run it rather than trusting this file.

```bash
cd backend && source .venv/bin/activate
python eval/run_eval.py --tolerance 1.5
```

## Read this first

**Four clips is not a validation set.** It is enough to catch a system that
has stopped working and enough to check the property that matters most — that
non-fall footage does not produce fall alerts — and nothing more. These are
engineering metrics. They establish nothing about clinical validity, and the
language policy in the README applies: these are *mobility risk indicators*,
not diagnoses.

The labels were produced by inspecting each clip at 1 fps and recording when
the labelled event visibly occurs. They are approximate to roughly ±0.5s,
which is why the default tolerance is ±1.5s.

Two of the four clips are **negative controls** with no labelled events. They
exist to measure false alarms, which is the failure mode that actually
destroys trust in a system like this.

## Clips

| Clip | Label | Contents |
|---|---|---|
| `warehouse-fall.mp4` | positive | A worker collapses to the floor at t≈3.5s; a colleague kneels to assist from t≈6s. |
| `assisted-walk-sit.mp4` | positive | An elderly person walks supported by two carers for ~11s, then is lowered into a chair at t≈13s. A controlled transition, **not** a fall. |
| `office-hallway-walk.mp4` | **negative** | One person walks steadily down a hallway for the whole clip. Nothing happens. |
| `two-person-approach.mp4` | **negative** | Two people walk side by side toward the camera. Nothing happens. Also exercises two simultaneous tracks. |

## Results

**Date:** 2026-08-17 · **Tolerance:** ±1.5s · **Hardware:** Apple M2, CPU inference

| Clip | Label | TP | FP | FN | Alerting events | Fall events |
|---|---|---|---|---|---|---|
| `assisted-walk-sit.mp4` | positive | 1 | 3 | 0 | 8 | 0 |
| `office-hallway-walk.mp4` | NEGATIVE | 0 | 0 | 0 | 2 | 0 |
| `two-person-approach.mp4` | NEGATIVE | 0 | 0 | 0 | 5 | 0 |
| `warehouse-fall.mp4` | positive | 1 | 0 | 0 | 6 | **1** |

Aggregate over the labelled event types:

| Metric | Value |
|---|---|
| Precision | 0.40 |
| Recall | 1.00 |
| F1 | 0.57 |
| False alarms / minute | 3.33 |
| Mean absolute timing error | 0.63 s |

**Negative-control check: 2 clips with no fall, 0 fall events emitted.**

## What these numbers mean

**Recall 1.00 with 0.63s timing error.** Both labelled events were found near
the right moment: the warehouse fall and the assisted sit-down. The
posture-collapse geometry in `_posture_collapse` is doing the work on the
fall — the subject is already horizontal when the detector reacquires them,
which pure motion-delta detection would miss.

**Zero false falls on the negative controls.** This is the number worth
caring about. Neither the hallway walk nor the two-person approach produced a
`Fall-like motion event`, and no clip produced one spuriously.

**Precision 0.40 is real and not tuned away.** All three false positives are
`Postural Transition` events on `assisted-walk-sit.mp4` at t≈5.9s, 8.4s and
9.7s, on three different tracks, during the *walking* phase. The clip shows an
elderly person moving slowly with pauses while supported on both sides, and
`_postural_transition` fires on exactly that signature: mean speed above the
slow threshold, recent speed near zero, moderate variance. It is not
misfiring on noise — it is detecting something that genuinely looks like a
deceleration to a stop, and the label says only the final sit counts.

That is a threshold question, and **four clips is not enough evidence to move
a threshold**, per ADR-010. Recorded here as a measured limitation. The right
fix is `SF1` in the finishing plan: sweep the thresholds over cached features
and pick an operating point against a larger labelled set.

## Change log

**2026-08-17 — camera-motion aggregation.** `assisted-walk-sit.mp4` was
emitting 19 separate `Abrupt trajectory change` rows for one hand-held camera
sequence, alongside 3 `Camera motion uncertainty` events identifying the
shared cause. When the scene itself is moving, per-track position variance has
a single scene-level explanation, so presenting it once per subject reports
one camera pan as a dozen independent findings.

`_display_events` now collapses `Abrupt trajectory change` into one row
carrying a count when camera motion was detected in the same clip.

Effect on alerting-event volume, detection unchanged:

| Clip | Before | After |
|---|---|---|
| `assisted-walk-sit.mp4` | 26 | 8 |
| `two-person-approach.mp4` | 7 | 5 |
| `warehouse-fall.mp4` | 7 | 6 |
| `office-hallway-walk.mp4` | 2 | 2 |

Precision, recall, F1 and timing error were **identical** before and after.
This is a presentation change; no detection threshold moved.

## Known gaps

- Four clips, all short (12–18s), all from stock footage.
- No occlusion-heavy, low-light, or crowded footage.
- Track identity is not evaluated: `run_eval.py` matches on event type and
  time only (`require_track_match=False`), because tracker IDs are assigned at
  runtime and cannot be known when labelling by hand. ID switches are
  therefore invisible to these metrics.
- Informational event types (slow walking, uncertainty rows) are excluded from
  precision, since the labels make no claim about them. Counting them as false
  positives would be dishonest in the other direction.
