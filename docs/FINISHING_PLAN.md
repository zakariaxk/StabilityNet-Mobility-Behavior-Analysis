# StabilityNet — Finishing Implementation Plan

> **Status 2026-08-17:** S1–S3, S5–S7, S10, S13, S14 are **implemented and
> merged to `finishing-plan-implementation`** (PR #4). Backend 49 → 56 tests,
> CI added and green, API response 1.6 MB → 105 KB, submission 11.6 s → 39 ms.
> Remaining: **S4** (normalization sprawl), **S8** (split the 1,700-line page
> component), **S9** (unify overlay tone with scorer physics — now unblocked,
> since S5 can prove no metric drift), **S11** (synthetic-frame pipeline
> integration test), **S12** (throughput benchmark), **S15** (remaining docs),
> **SF1/SF2** (threshold sweep, synced timeline).
> Deployment stays local by design — see §9.

Audit date: 2026-08-17 · Repo @ `0e6ca70` (clean)
Companion plan for the sibling project: `Waypoints/docs/FINISHING_PLAN.md`

Baseline established by running, not by reading:

| Check | Result |
|---|---|
| `python -m pytest -q` (backend) | **49 passed + 6 subtests / 5.75s** (README says 26 — stale) |
| `frontend` tests | 1 vitest file, 1 suite (README says "No test suite" — stale) |
| `du -sh backend/outputs` | **1.0 GB** across 34 analyses; largest record **6.3 MB** |
| CI workflow | **none exists** |

---

## 1. Executive Assessment

| | |
|---|---|
| **Completeness** | **~75%**. The CV pipeline is complete and genuinely works end-to-end; the API and frontend are thin over it, and the presentation layer is fragile. |
| **Technical strength** | The behavior layer. `app/behavior/features.py` computes ten explainable temporal features over a sliding window with no model dependency, so it is unit-testable without OpenCV or torch — and it is (`tests/test_features.py`, `test_scoring.py`). The posture-collapse geometry (`scoring.py:_posture_collapse`) is a real insight: it catches falls where the detector first sees the subject already horizontal, which pure motion-delta detection misses. The reliability policy (`_finalize_analysis_policy`) that separates raw counts from displayed counts is mature thinking. |
| **Biggest weakness** | **The API returns the entire per-frame trace to the browser.** `video_pipeline.py:341` puts `frames` (every detection, track, and feature dict for every frame) into `result`, `analysis_service._public_result` passes it through, and `page.tsx:131` parses it client-side. Measured: analysis records on disk are up to **6.3 MB**, `backend/outputs/` totals **1.0 GB**. Every analysis ships multiple MB over the wire for data the UI barely uses. |
| **Biggest opportunity** | The evaluation seam. `app/evaluation/metrics.py` already implements one-to-one temporal matching with precision/recall/F1/false-alarms-per-minute — and nothing calls it. Wiring 4 labeled sample clips into an eval target converts "I tuned thresholds until the demo looked right" into "here are measured numbers on held-out clips." That is the single biggest credibility upgrade available to this project. |

---

## 2. Current Architecture

```
backend/ (Python 3.11+, FastAPI, sync endpoints)
  app/main.py            create_app(); CORS; mounts /outputs static; app.state.analysis_service
  app/api/routes.py      GET /health · POST /analyses · POST /analyses/upload
                         GET /analyses/{id} · GET /analyses/{id}/video      ← all `def`, not `async def`
  app/api/analysis_service.py (652)  upload persistence, _normalize_result, _summarize_result
  app/pipeline/video_pipeline.py (964)  analyze_video() — the orchestrator
  app/pipeline/frame_reader.py   OpenCV VideoCapture, stable index/fps timestamps
  app/pipeline/annotated_video.py (832)  OpenCV overlay → ffmpeg libx264/yuv420p/+faststart
  app/vision/yolo_detector.py (386)  Ultralytics YOLO26n, module-level model cache + Lock,
                                     640px analysis downscale, auto-download of weights
  app/vision/sort_tracker.py     greedy max(IoU, center-distance), EMA bbox smoothing α=0.62
  app/behavior/{track_state,features,scoring}.py   history → 10 features → threshold events
  app/evaluation/metrics.py      precision/recall/F1/FA-per-min  ← IMPLEMENTED, NEVER CALLED
  app/config.py (288)    env-driven PipelineConfig / DetectorConfig / BehaviorConfig
  app/cli.py             `python -m app.cli analyze --video --output [--detector-model]`
  tests/ (10 files, 49 tests, pure-Python — no cv2/torch required)
frontend/ (Next.js 16, React 19, TS 6)
  src/app/page.tsx (1749)   the entire UI, one client component
  src/app/globals.css (2610)
  src/app/api/stabilitynet/**  6 route handlers proxying to FastAPI (browser never hits :8000)
  src/lib/{stabilityNetApi,backendProxy,analysisPresentation,sampleVideos}.ts
```

Storage is the filesystem: `outputs/analyses/*.json` (record + `.result.json`), `outputs/uploads/<uuid>/clip.mp4`, `outputs/videos/<uuid>.mp4`.

---

## 3. What Works / What Doesn't

### Works (verified)

- **The whole pipeline, end to end.** Decode → detect → track → accumulate → featurize → score → annotate → transcode → persist, in one readable orchestrator. Committed sample MP4s exist at `backend/samples/` and 34 completed analysis records are on disk. This runs.
- **Behavior math is model-free and tested.** `features.py` is pure Python over `TrackPoint` lists; `scoring.py` takes a frozen dataclass. 49 tests run without OpenCV, torch, or weights — a deliberate and correct architectural choice (`docs/EVALUATION.md`).
- **Posture-collapse detection.** `_posture_collapse` compares current bbox aspect ratio against a baseline from the first 6 confirmed observations. This catches the case pure motion-delta detection structurally cannot: the detector's first sight of the subject is already horizontal.
- **Reliability policy separated from raw output.** `_finalize_analysis_policy` / `_scene_reliability` / `_display_events` keep raw counts for debugging while presenting only qualified subjects and suppressing weak events. `_normalize_display_event` downgrades `high` → `review_needed` when scene reliability is Low. `test_pipeline_policy.py` covers it.
- **FPS metrics are honestly disambiguated.** Five distinct fields with comments explaining exactly what each measures and why `processing_fps` is aliased to end-to-end rather than inference throughput. This is the opposite of the usual FPS overclaim.
- **Frontend proxy with correct range handling.** `proxyBackendVideoResponse` forwards `Range`/`If-Range` and passes back `accept-ranges`/`content-range` — the thing that actually breaks Safari/Chrome seeking if you get it wrong.
- **Model loading.** Module-level cache behind a `Lock`, auto-download with an explicit manual-fallback error message, device selection with a clear failure when `mps`/`cuda` is requested and unavailable.

### Partially implemented

- **Evaluation.** `evaluate_events()` is complete and unit-tested. Nothing calls it. No labeled clips exist, no runner, no manifest, no reported numbers. `docs/EVALUATION.md` even names the missing piece: "A future manifest runner can aggregate these per-clip results once timestamp labels exist."
- **CLI.** README documents `--annotated-video outputs/annotated.mp4` (README lines 212-216) — **`build_parser()` has no such argument** (`cli.py:29-41`). Copying the documented command fails with an argparse error, and the CLI cannot produce annotated video at all. Documentation/code discrepancy; trust the code.

### Unfinished / dead

- **Three orphaned event generators** in `video_pipeline.py`: `_track_end_events` (line 807, imported by `test_pipeline_policy.py` but never called by `analyze_video`), `_camera_motion_uncertainty_event` (851), `_insufficient_evidence_event` (912). None are wired into the frame loop.
- **Consequence:** `_scene_reliability` (line 603) subtracts 0.25 and appends "camera motion uncertainty" when it counts `Camera motion uncertainty` events — **which can never exist**, because the only function that creates them is never called. That branch is unreachable. Likewise "Insufficient visual evidence" and "Subject leaving frame" appear in `_display_events`' allowlist, `_event_severity`, and `_default_event_description`, but nothing emits them.
- **No list endpoint.** Records accumulate on disk with no `GET /analyses`; the UI cannot show history.

### Broken or fragile

1. **Multi-megabyte responses.** `result["frames"]` holds a dict per frame with every detection, track, and feature. `_public_result` strips only `video.path`. Records reach **6.3 MB**; `page.tsx:131` (`buildTrackRows(tracks, analysis?.result?.frames, events)`) parses them in the browser. This is the project's dominant performance problem and it is entirely self-inflicted — `tracks[].trajectory` already contains what the UI actually draws.
2. **Synchronous analysis in the request.** `POST /analyses/upload` blocks until the full pipeline (including ffmpeg transcode) completes. Because the routes are `def` not `async def`, FastAPI runs them in the threadpool so the event loop survives — but there is no job id, no progress, no cancel, and no bound on concurrent analyses. Two simultaneous uploads contend for CPU with no queue. ADR-005 consciously accepted this for Phase 2; it is now the main thing standing between the project and feeling finished.
3. **Fake progress UI.** `PROCESSING_STAGES` in `page.tsx:32` advances on a 1800ms `setInterval` with no relationship to backend state. It is a placeholder, and on a slow video it sits on "Preparing annotated output…" for minutes.
4. **Defensive-normalization sprawl.** `analysis_service.py` carries `_normalize_result`, `_summarize_result`, `_public_result`, `_normalize_tracks`, `_normalize_events`, plus `_event_type_label` and `_default_event_description` that **duplicate** functions of the same names in `video_pipeline.py` with divergent mappings. There are ~15 FPS field aliases each with multi-level fallbacks. This is a schema-uncertainty tax paid at every layer, and it is why `page.tsx` also has 4-deep `??` chains (`page.tsx:142-164`).
5. **Overlay logic duplicates scorer logic.** `annotated_video._risk_tone()` reimplements posture collapse, fall-like motion, and postural transition from raw features "independently of the event scorer" (README:105). The README documents this as deliberate, but it means the same physics is expressed twice and can drift — a threshold change in `scoring.py` silently desynchronizes the video overlay from the event list.
6. **Video reopened twice.** `VideoFrameReader.metadata()` opens and releases a capture, then `frames()` opens another. Harmless but wasteful.
7. **Full-body buffering in the proxy.** `proxyBackendRequest` does `await response.arrayBuffer()` — a non-range video request loads the entire MP4 into the Next.js process's memory before responding.
8. **Reproducibility gap.** `backend/samples/*` and `backend/outputs/` are gitignored, thumbnails are gitignored, and weights are gitignored. A fresh clone has an app with four sample cards that all fail. `MANUAL_ACTIONS.md` §14 acknowledges this but the fix is manual and undocumented in the README.
9. **1.0 GB of local output** with no retention policy.

### Technically strong already — leave alone

`app/behavior/*` · `app/vision/sort_tracker.py` · `app/config.py` · `app/evaluation/metrics.py` · the Next.js proxy-route architecture · the frontend/backend boundary. Do not restructure these.

### What prevents it feeling complete

You upload a video and stare at a fake progress bar for minutes, then receive several megabytes of JSON. The thresholds that drive every conclusion have never been measured against a label. And a reviewer who clones the repo cannot run the demo.

---

## 4. Finishing Roadmap

### Phase 0 — Verify baseline

**S0.** **Priority: do first. Difficulty: Small.**
```bash
cd backend && source .venv/bin/activate
python -m pytest -q            # expect 49 passed + 6 subtests
python smoke_test.py           # confirms weights load + CPU inference
python -m app.cli analyze --video samples/warehouse-fall.mp4 --output outputs/base.json
python -c "import json;d=json.load(open('outputs/base.json'));print(d['frames_processed'],d['qualified_subject_count'],d['mobility_event_count'],d['cpu_analysis_throughput_fps'])"
du -h outputs/base.json        # ← record this; it is the S1 acceptance baseline
cd ../frontend && npm run typecheck && npm run test && npm run build
```
Record: per-sample event counts, throughput FPS, and record size. These are the before-numbers for S1 and S12.
Note: the README's `--annotated-video` flag does not exist — expect that command to fail (this is S3).

---

### Phase 1 — Fix correctness and payload

**S1. Stop shipping the per-frame trace to clients.** **Priority: P0. Difficulty: Medium. Blocks: S6, S8.**
- Files: `app/pipeline/video_pipeline.py`, `app/api/analysis_service.py`, `frontend/src/app/page.tsx`, `frontend/src/lib/stabilityNetApi.ts`.
- Wrong: `result["frames"]` (every detection/track/feature per frame) flows through `_public_result` into the HTTP response; `page.tsx` parses it.
- Implementation: keep writing the full trace to `outputs/analyses/<id>.result.json` on disk — it is genuinely useful for debugging and costs nothing there. Drop `frames` from `_public_result`. Add a `GET /analyses/{id}/frames` endpoint that serves it for the debug case only. On the client, delete `observationsFromFrames` (`page.tsx:1349`) and the `frames` argument to `buildTrackRows` — `tracks[].trajectory` already carries the points the UI draws, and `parseTrajectoryPoints` already handles it.
- Why: 6.3 MB → tens of KB on the wire, and it removes a whole client-side parsing path.
- Acceptance: for `warehouse-fall.mp4`, the `POST /analyses/upload` response body is **< 250 KB** (measure with `curl -o /dev/null -w '%{size_download}'`); the tracks table, trajectories, event timeline, and video all still render identically; `outputs/analyses/<id>.result.json` still contains `frames`.

**S2. Resolve the dead event generators — wire or delete.** **Priority: P1. Difficulty: Medium. Depends: none.**
- File: `app/pipeline/video_pipeline.py`.
- Decide per function, and make `_scene_reliability` consistent either way:
  - `_camera_motion_uncertainty_event` — **wire it.** Call it once per analysis frame with `previous_analysis_observations` and the current observations. It is the only handheld/pan detector in the system, it is already written and coherent, and `_scene_reliability` already has a branch waiting for it. This makes the reliability score actually reflect camera motion instead of scoring a condition it can never observe.
  - `_track_end_events` — **wire it.** Call it on each analysis frame comparing previous vs current track ids. It produces "Track ended near frame boundary" and "Insufficient visual evidence", both already handled in `_display_events`, `_event_severity`, and `_default_event_description`. It is also the only function currently covered by `test_pipeline_policy.py` that production never executes.
  - `_insufficient_evidence_event` — **delete it.** It duplicates the low-confidence branch of `_track_end_events` and would fire per-frame rather than once at track end, flooding the event list.
- Why: the largest correctness gap in the pipeline — a documented scoring input (`camera motion uncertainty`, worth −0.25 reliability) that is structurally unreachable.
- Acceptance: analyzing a handheld/panning clip produces at least one `Camera motion uncertainty` event and a reduced `scene_reliability_score` with that reason listed; a clip where a subject walks out of frame produces `Track ended near frame boundary`; `test_pipeline_policy.py` passes and gains a case asserting `analyze_video` (not just the helper) emits both.

**S3. Fix the CLI/README discrepancy.** **Priority: P1. Difficulty: Small. Blocks: S5, S12.**
- File: `app/cli.py`.
- Add the `--annotated-video` argument the README already documents and pass it as `AnalysisRequest.annotated_video_path`. This also makes the CLI usable for the evaluation harness (S5) and the benchmark (S12) without booting the API.
- Acceptance: `python -m app.cli analyze --video samples/warehouse-fall.mp4 --output /tmp/r.json --annotated-video /tmp/a.mp4` produces both files; `ffprobe /tmp/a.mp4` shows `codec_name=h264`, `pix_fmt=yuv420p`. `test_cli.py` gains a case.

**S4. Collapse the normalization sprawl.** **Priority: P2. Difficulty: Medium. Depends: S1.**
- Files: `app/api/analysis_service.py`, `app/api/schemas.py`, `app/pipeline/video_pipeline.py`.
- This is the one refactor that passes the preserve-working-code test: it is *causing* the problem (4-deep `??` chains in `page.tsx`, two divergent copies of `_event_type_label`, ~15 FPS aliases), it cannot be fixed locally, and the regression risk is bounded by the existing `test_api.py`.
- Scope it tightly: (a) delete `_event_type_label` and `_default_event_description` from `analysis_service.py` and import the `video_pipeline` versions — they are the ones the pipeline actually applies; (b) pick **one** canonical name per FPS concept (`source_video_fps`, `effective_analysis_fps`, `cpu_analysis_throughput_fps`, `end_to_end_processing_fps`, `playback_fps`) and drop the aliases from the *response* while keeping them in the on-disk record for backward compatibility with the 34 existing files; (c) make `AnalysisRecord` in `schemas.py` the single contract and delete the fallback chains in `_summarize_result` that exist only because the shape was uncertain.
- Do **not** touch `_finalize_analysis_policy`, `_normalize_display_event`, or the behavior modules.
- Acceptance: `test_api.py` passes; `page.tsx`'s `??` chains for `trackCount`/`eventCount`/`framesProcessed` reduce to a single field each; existing records on disk still load via `GET /analyses/{id}`.

---

### Phase 2 — Complete the product flow

**S5. Wire the evaluation harness. (The highest-value task in this project.)** **Priority: P0. Difficulty: Medium. Depends: S3.**
- New: `backend/eval/labels/*.json` (one per sample clip), `backend/eval/run_eval.py`, `docs/EVALUATION_RESULTS.md`.
- Hand-label the four committed sample clips with `{event_type, track_id, timestamp_s}` ground truth — watch each clip, note when the fall / sit-down / stop actually happens. Four clips is enough to be honest; it is not enough to claim generalization, and the doc must say so.
- `run_eval.py` runs `analyze_video` per clip via the CLI path, maps predictions into `EvaluationEvent`, calls the **already-written** `evaluate_events(..., tolerance_s=1.0)`, and prints a per-clip + aggregate table.
- Commit results with the tolerance and the clip count stated, per `docs/EVALUATION.md`'s own guidance.
- Why: `docs/DECISIONS.md` ADR-010 says heuristic changes "should be justified against labeled held-out clips" — and there are none, so every threshold in `scoring.py` is currently justified by demo impressions. This single task converts the project's core claim from anecdote to measurement, and the metric implementation already exists and is tested. It is also the answer to "how do you know your thresholds are right?", which is the first question any reviewer asks about a heuristic CV system.
- Acceptance: `python eval/run_eval.py` prints precision/recall/F1/FA-per-minute per clip and aggregate; `docs/EVALUATION_RESULTS.md` records the numbers, the tolerance, the clip count, and an explicit "4 clips is not a validation set" caveat.

**S6. Make analysis a background job with real progress.** **Priority: P0. Difficulty: Medium. Depends: S1.**
- Files: `app/api/routes.py`, `app/api/analysis_service.py`, `frontend/src/app/page.tsx`, new proxy route.
- Wrong: the upload request blocks for the full pipeline; the client shows a timer-driven fake progress bar.
- Implementation, kept small and dependency-free: `POST /analyses/upload` saves the file, creates the record with `status: "processing"`, and submits `_run_analysis` to a **module-level `ThreadPoolExecutor(max_workers=1)`** (serializing analyses is correct here — they are CPU-bound and contending workers make everything slower), then returns `202 { analysis_id, status: "processing" }`. `analyze_video` gains an optional `progress_callback(frames_processed, total_frames, stage)` invoked from the existing frame loop; the service writes `{status, progress, stage}` into the record JSON. `GET /analyses/{id}` returns it. Client polls every 1s and drives the **existing** `ProcessingPanel` from real numbers; delete the `setInterval` at `page.tsx:114`.
- No Celery, no Redis, no database. A `ThreadPoolExecutor` plus the JSON files already on disk is the whole job system, and it is proportionate to a single-machine local tool.
- Why: removes the two most demo-damaging behaviors at once — the multi-minute dead wait and the lying progress bar. Also unblocks a "cancel" affordance and makes concurrent uploads well-defined instead of accidental.
- Acceptance: uploading a 20s clip returns `202` in **< 500ms**; the UI shows a monotonically increasing real percentage; two simultaneous uploads both complete (queued, not interleaved); killing and restarting the backend mid-analysis leaves the record in `processing` and a subsequent `GET` reports it (stale-job handling documented, not silently hidden).

**S7. Add `GET /analyses` and a history view.** **Priority: P2. Difficulty: Small. Depends: S1, S6.**
- 34 records already exist on disk and are unreachable through the UI. Add a paginated list (id, created_at, filename, subject count, event count, top severity), the proxy route (`frontend/src/app/api/stabilitynet/analyses/route.ts` currently handles POST only), and a sidebar list that loads a past analysis.
- Why: makes the persistence that already exists visible, and lets the demo show a prepared result instantly instead of waiting for a live run.
- Acceptance: past analyses list and load; the annotated video and event timeline render from a record created before the change.

**S8. Split `page.tsx`.** **Priority: P2. Difficulty: Medium. Depends: S1, S6.**
- 1749 lines in one client component. Extract along boundaries that already exist as functions: `UploadPanel`, `SamplePicker`, `SummaryCards`, `AnnotatedVideoPlayer` (+`EventMarkers`), `TracksTable`, `EventsTable`, and a `lib/analysisSelectors.ts` for the ~20 pure parsing helpers at the bottom of the file (`buildTrackRows`, `parseTrajectoryPoints`, `summarizeTrackMotion`, …).
- Mechanical extraction, not redesign — the components are already written as standalone functions. Do it **after** S1 removes the frame-parsing path so you are not moving code you are about to delete.
- Acceptance: no file over ~400 lines; `npm run build` and the vitest suite pass; UI visually unchanged; the extracted selectors gain unit tests (S11).

---

### Phase 3 — Strengthen where justified

**S9. Unify overlay tone with scorer physics.** **Priority: P1. Difficulty: Medium. Depends: S5.**
- Files: `app/behavior/scoring.py`, `app/pipeline/annotated_video.py`.
- `_risk_tone()` reimplements `_posture_collapse`, `_fall_like_motion`, and `_postural_transition` from raw features. Export those three predicates from `scoring.py` and have `_risk_tone` call them. Keep the overlay's *policy* (cooldown-free, instantaneous, boundary/confidence gating) exactly as-is — only the physics predicates are shared.
- Why: it is causing a real drift risk (a threshold edit in one file silently desynchronizes the annotated video from the event list, exactly the kind of inconsistency a viewer notices), it cannot be fixed locally, and the change is a pure extraction with `test_scoring.py` as the regression net.
- Do this **after** S5 so you can prove event output is unchanged by measurement, not by inspection.
- Acceptance: `test_scoring.py` and `test_annotated_video.py` pass; re-running S5's eval produces identical metrics; a new test asserts `_risk_tone` and `EventScorer` agree on a synthetic posture-collapse feature set.

**S10. Retention and repo hygiene.** **Priority: P2. Difficulty: Small.**
- `backend/outputs/` is 1.0 GB. Add `python -m app.cli prune --keep 10` (or a small `scripts/prune_outputs.py`) that deletes all but the N most recent analyses with their uploads and videos.
- Commit real 320px thumbnails to `frontend/public/samples/thumbnails/` (currently gitignored, so the sample cards render fallbacks on a fresh clone). A few KB each.
- Acceptance: `du -sh backend/outputs` under 200 MB after prune; fresh clone shows real thumbnails.

---

### Phase 4 — Testing and measurement

**S11. Targeted tests for the gaps.** **Priority: P1. Difficulty: Medium. Depends: S2, S6.**
- Backend: pipeline-level tests that `analyze_video` emits camera-motion and track-end events (S2 wired them, but the existing tests only exercise the helpers directly); job-state transitions for S6; a synthetic-frame integration test using a generated video (`cv2.VideoWriter` of moving rectangles) so the full loop runs in CI without the model — use a **stub detector** injected via `DetectorConfig`, per the project's existing "test inference logic separately from the model" principle.
- Frontend: extend the one existing vitest file to cover the selectors extracted in S8 (`buildTrackRows`, `parseTrajectoryPoints`, `summarizeTrackMotion`) — these are pure and are where the display bugs live.
- Acceptance: backend ≥ 60 tests, frontend ≥ 15, both in CI (S13).

**S12. Reproducible throughput benchmark.** **Priority: P1. Difficulty: Small. Depends: S3.**
- New: `backend/bench/throughput.py` — runs the four sample clips at `STABILITYNET_ANALYSIS_TARGET_FPS` ∈ {12, 22, 30} on the configured device, reporting for each: `cpu_analysis_throughput_fps`, `effective_analysis_fps`, `end_to_end_processing_fps`, and the `timing_seconds` breakdown (decode/inference/tracking/event/annotation/encode) the pipeline **already collects**.
- Commit `docs/BENCHMARK.md` with the machine spec (chip, RAM, device=cpu/mps).
- Why: the README's "approximately 22 FPS" is a *configured target*, not a measurement (see §6). This makes it a measured number, and the timing breakdown tells you whether inference or ffmpeg is the real cost — which you currently do not know.
- Acceptance: `docs/BENCHMARK.md` exists with real per-stage numbers and named hardware.

---

### Phase 5 — Polish, deployment, demo

**S13. Add CI.** **Priority: P1. Difficulty: Small.**
- StabilityNet has **no CI workflow** (the sibling project does). Add `.github/workflows/ci.yml`: `pytest` (no model needed — the suite is model-free), `ruff` or `flake8`, then `cd frontend && npm ci && npm run typecheck && npm run lint && npm run test && npm run build`.
- Acceptance: green check on PRs.

**S14. Make a fresh clone runnable.** **Priority: P1. Difficulty: Small. Depends: S10.**
- Add `backend/scripts/bootstrap.sh` that creates the venv, installs, checks for ffmpeg with the right per-OS message, and runs `smoke_test.py` (which already auto-downloads weights). **Skip Docker** — torch + ultralytics + opencv is a ~3 GB image, and two documented terminal commands are faster and clearer for a local-first tool.
- Fix the README discrepancies found in this audit: "26 tests" → 49+; "No test suite" for the frontend → 1 vitest file; the `--annotated-video` CLI example (S3 makes it true).
- Acceptance: a clean clone reaches a working demo in under 10 minutes following only the README.

**S15. Docs sync.** **Priority: P2. Difficulty: Small.**
- `docs/AGENT_STATE.md` says "Current Phase: Phase 2" and lists "Next: run the full pipeline against a real uploaded MP4" — 34 completed analyses say that shipped long ago. `docs/ROADMAP.md` Phase 3 proposes Redis + PostgreSQL; mark it deferred (S6 solves the job problem without either). Add ADRs for the S6 threadpool decision and the S1 payload split.

---

## 5. Features Worth Adding

Two.

**SF1. Threshold sensitivity view (depends on S5).** Once labeled clips exist, add a `--sweep` mode to the eval runner that re-scores the *already-extracted* features across a grid of `unstable_variance_threshold_px2` / `dwell_time_threshold_s` / posture-collapse values and plots precision-recall. Surface the chosen operating point in the UI as "sensitivity: conservative / balanced / sensitive" mapped to three `BehaviorConfig` presets.
- Why materially better: the honest answer to "why these numbers?", and it turns a bag of magic constants into a defensible operating point. Strengthens the *technical* story more than any new feature could, and costs almost nothing because feature extraction is already decoupled from scoring — you re-score cached features, you do not re-run YOLO.
- Cost: ~150 lines + a settings control. **After** S5.

**SF2. Per-subject event timeline synced to the video.** The UI has an event list and a video; clicking an event already seeks (`seekToTimestamp`, `page.tsx:174`). Extend to a horizontal timeline lane per qualified subject, with severity-colored markers and a playhead, plus a trajectory sparkline that highlights the segment under the playhead.
- Why materially better: makes the *temporal* nature of the analysis visible, which is the actual thesis of the project ("temporal motion windows"), and it is the highest-impact demo upgrade per line of code. All the data (`tracks[].trajectory` with timestamps, `events[].timestamp_s`) is already in the response.
- Cost: ~250 lines. **After** S1 and S8.

## 6. Things NOT Worth Building

| Idea | Why not |
|---|---|
| **Redis + PostgreSQL** (`docs/ROADMAP.md` Phase 3) | S6's `ThreadPoolExecutor` + JSON files solves the actual problem (blocking requests, no progress) for a single-machine tool. A database adds ops burden and zero capability here. |
| **Live webcam / real-time streaming inference** | Sounds impressive, is a different product. WebRTC ingest + frame pacing + a stateful session model is more work than everything else on this roadmap combined, and CPU YOLO cannot keep up with live video anyway. `MANUAL_ACTIONS.md` §18 already commits to describing this honestly as uploaded-video analysis — keep that. |
| **Training a custom model / fine-tuning YOLO** | No labeled dataset, no compute budget, and person detection is a solved problem. The interesting work is the temporal/behavioral layer, which is already yours. |
| **Kalman filter + Hungarian assignment tracker** | ADR-003 defers this until identity switches are *measured*. They have not been. Do S5 first; if the metrics show ID-switch-driven false negatives, revisit — otherwise the greedy tracker with center-distance fallback is working. |
| **Pose estimation (keypoints) for better fall detection** | Genuinely would improve accuracy, and genuinely doubles the inference cost and the feature layer. Out of scope for finishing; a legitimate "future work" line in the README. |
| **Rewriting `globals.css` (2610 lines) into Tailwind/CSS modules** | It works and looks good. Pure churn with visual-regression risk. |
| **Docker image for the backend** | torch + ultralytics + opencv ≈ 3 GB. Two documented terminal commands beat a slow image. |
| **Multi-camera / calibration / real-world gait speed** | `docs/EVALUATION.md` already correctly defers all of these. Pixel-space metrics with an honest caveat is the right scope. |
| Replacing FastAPI / Next.js / Ultralytics | Nothing wrong with any of them. |

---

## 7. Testing Plan

| Layer | What | Where | Why here |
|---|---|---|---|
| **Unit — behavior** | Feature math, scoring thresholds, tracker IoU/expiry (exists, 49 tests, model-free) | `backend/tests/` | Already the strongest part. Keep it model-free. |
| **Unit — pipeline policy** | Qualification, event merge, scene reliability (exists). **Add (S11):** assertions against `analyze_video` itself, not only the helpers — S2 exists because helpers were tested while production skipped them. `LESSONS.md` already records this exact lesson. | `test_pipeline_policy.py` | |
| **Integration — inference-free** | Full `analyze_video` over a synthetic `cv2.VideoWriter` clip with a **stub detector** (moving rectangles → known bboxes). Asserts the frame loop, stride, tracking, overlay, and JSON write all run in CI without weights. | new `test_pipeline_integration.py` | Only way to test the orchestrator in CI. |
| **Integration — API** | Exists with a fake runner (`test_api.py`). **Add (S6):** 202 + job-state transitions; **(S1):** response has no `frames`; **(S7):** list endpoint. | `test_api.py` | |
| **CV evaluation (S5)** | Labeled clips → precision/recall/F1/FA-per-min/timing error, at a stated tolerance. Not a unit test — a reported measurement. | `backend/eval/` + `docs/EVALUATION_RESULTS.md` | **The most important testing work in this project.** |
| **Frontend** | Selectors extracted in S8. Keep the existing severity-presentation test — it correctly encodes "unknown severity must fail toward review," a real safety property. | `frontend/src/lib/*.test.ts` | |
| **E2E smoke** | `bootstrap → uvicorn → CLI analyze one sample → assert record fields + annotated MP4 codec via ffprobe`. Runs locally, not in CI (needs weights + ffmpeg). | `scripts/smoke_e2e.sh` | |
| **Not worth testing** | YOLO accuracy, ffmpeg internals, CSS. | | Third-party or unmeasurable. |

Not chasing a coverage percentage.

---

## 8. Performance Validation Plan

| Claim | Source | Verdict | Action |
|---|---|---|---|
| "analysis runs at approximately 22 FPS" | `README.md:31` | **Misleading as stated.** 22 FPS is `STABILITYNET_ANALYSIS_TARGET_FPS` — a *configured sampling cadence* that sets the frame stride, not measured throughput. Actual measured throughput is `cpu_analysis_throughput_fps`, a different and unpublished number. The README's own FPS table (lines 356-367) explains this distinction correctly, then the detection section states 22 FPS without it. | **S12** publishes measured numbers; reword §Detection to "samples at a target 22 FPS (configurable); measured throughput in `docs/BENCHMARK.md`." |
| Per-run FPS fields (`cpu_analysis_throughput_fps`, `end_to_end_processing_fps`, …) | `video_pipeline.py:249-271` | **Directly supported.** Genuinely measured with `time.perf_counter()` around the real loop, and carefully disambiguated in code comments. This is the honest part. | Keep; publish. |
| "Every component is independently testable" | `README.md:21` | **Directly supported** — 49 tests run with no cv2/torch/weights. | None. |
| "26 tests" | `README.md:285` | **Stale** — 49 pass + 6 subtests. | S14. |
| "Frontend: No test suite" | `README.md:295` | **Stale** — vitest + `analysisPresentation.test.ts` exist. | S14. |
| CLI `--annotated-video` flag | `README.md:212` | **Unsupported** — the argument does not exist in `cli.py`. | **S3.** |
| Scene reliability accounts for camera motion (−0.25) | `video_pipeline.py:603`, README | **Currently unsupported** — the only producer of `Camera motion uncertainty` events is never called, making the branch unreachable. | **S2.** |
| Threshold values in `BehaviorConfig` | `README.md:390-403` | **Plausible but not validated.** Every number is hand-tuned against four demo clips. ADR-010 explicitly forbids this and asks for labeled metrics — which do not exist. | **S5.** |
| "API integration with a fake pipeline runner" | `README.md:285` | **Directly supported** (count aside). | None. |

**Benchmark (S12), deliberately small:** re-uses the `timing_seconds` breakdown the pipeline already produces. Four clips × three target-FPS settings on the configured device; report per-stage ms, throughput, and hardware in `docs/BENCHMARK.md`. **No** profiling framework, no perf dashboard.

---

## 9. Deployment / Demo Readiness

### Today

Requires: Python 3.11+, venv, `pip install -e ".[dev]"` (pulls torch — several minutes and ~2 GB), ffmpeg on PATH, `yolo26n.pt` (auto-downloads via `smoke_test.py`), sample MP4s that are **gitignored**, thumbnails that are **gitignored**. `MANUAL_ACTIONS.md` is thorough but 500+ lines and mixes first-run setup with debugging.

### Target

```bash
# terminal 1
cd backend && ./scripts/bootstrap.sh     # venv + deps + ffmpeg check + weights via smoke_test
source .venv/bin/activate && uvicorn app.main:app --port 8000
# terminal 2
cd frontend && npm install && npm run dev        # :3000, proxies to 127.0.0.1:8000
```
Env: `STABILITYNET_DETECTOR_DEVICE=cpu` (default), `STABILITYNET_API_BASE_URL` for the frontend. Everything else optional.
Model files: auto-downloaded; document the manual URL fallback (already done well).
Samples: commit the four MP4s if each is under ~10 MB, or add `scripts/fetch_samples.sh`. **Commit the thumbnails regardless** — a fresh clone currently shows four broken sample cards, the first thing a reviewer sees.
Docker: **no.** A torch image is ~3 GB and adds nothing for a local tool.
Hosting: keep it local. CPU inference on a free tier is unusable, and the demo is stronger as "clone and run" with a committed annotated-output video + `docs/EVALUATION_RESULTS.md` in the README than as a slow hosted page.
Demo script: pick a past analysis from history (S7, instant) → point at the fall event → click it to seek the annotated video → show `EVALUATION_RESULTS.md` for "how do you know it's right."

---

## 10. Final Recommended Scope

### Ship StabilityNet With

1. Upload or sample-select an MP4; **background job with real progress**; history list of past analyses.
2. YOLO26n person detection (CPU-first, MPS/CUDA opt-in), 640px analysis downscale, auto-downloading weights.
3. SORT-style tracking with IoU + center-distance matching and bbox smoothing.
4. Ten explainable temporal features over a 5s sliding window per track.
5. Heuristic event scoring including posture-collapse fall detection, with cooldowns and merging.
6. **Camera-motion and track-end uncertainty events actually wired in**, so scene reliability reflects what it claims to.
7. Reliability policy: raw vs qualified subjects, suppression reasons, severity downgrade under low reliability, never-fail-toward-green.
8. Annotated H.264/yuv420p output with per-subject overlays, **whose risk tone shares physics with the event scorer**.
9. Compact JSON API (**no per-frame trace on the wire**; full trace on disk and behind a debug endpoint).
10. Next.js review UI: summary cards, tracks table with trajectories, event timeline synced to video playback, honest medical disclaimer.
11. **Labeled evaluation on the sample clips** with precision/recall/F1/false-alarms-per-minute at a stated tolerance, plus the "4 clips is not a validation set" caveat — and a threshold-sensitivity sweep.
12. `docs/BENCHMARK.md` with measured per-stage timings on named hardware.
13. Working CLI (including `--annotated-video`), ~60 backend tests, ~15 frontend tests, CI.
14. A fresh clone that reaches a working demo in under 10 minutes.

### Execution Order (StabilityNet only)

| # | Task | Why here |
|---|---|---|
| 1 | **S0** Verify baseline, record record-size + throughput | Before-numbers for S1 and S12. |
| 2 | **S1** Strip per-frame trace from responses | Unblocks S6/S8; biggest single perf win. |
| 3 | **S3** Fix CLI `--annotated-video` | Unblocks S5 and S12. |
| 4 | **S2** Wire camera-motion + track-end events; delete the third | Removes the pipeline's largest correctness gap. |
| 5 | **S5** Wire the evaluation harness + label 4 clips | **Highest-credibility task in the project.** |
| 6 | **S6** Background jobs + real progress | Kills the fake progress bar and the dead wait. |
| 7 | **S9** Unify overlay tone with scorer physics | Safe now that S5 can prove no metric drift. |
| 8 | **S4 / S7** Normalization cleanup, `GET /analyses` + history | Cleanup + makes existing persistence visible. |
| 9 | **S11 / S13** Pipeline + API tests, add CI | |
| 10 | **S12** Throughput benchmark → `docs/BENCHMARK.md` | Replaces the 22-FPS ambiguity with measurement. |
| 11 | **S8 / S10** Split `page.tsx`, output retention + commit thumbnails | |
| 12 | **SF1 / SF2** Threshold sensitivity presets, synced event timeline | Best demo/technical payoff, once the base is finished. |
| 13 | **S14 / S15** Bootstrap script, README corrections, docs sync | Do last, when the numbers are final. |

Items 1–6 reach *correct and complete*. Items 7–11 reach *defensible*. Items 12–13 are the polish that makes it look intentional rather than expanded.

### Interleaving with Waypoints

The two projects share no code, no language, and no runtime. See `Waypoints/docs/FINISHING_PLAN.md` for its own ordering. A combined cadence that keeps both moving without context-thrash:

1. W0 + S0 (both baselines)
2. W1, W2, W3 (cheap Waypoints correctness)
3. S1, S3 (cheap StabilityNet correctness/unblocks)
4. W4, W5 · then S2
5. **W7** (Waypoints big push) · then **S5** (StabilityNet big push)
6. W8 · S6
7. Remaining hardening, tests, benchmarks, polish per each plan's own order.
