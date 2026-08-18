"""Run the analysis pipeline over labelled clips and report event metrics.

This is the seam docs/DECISIONS.md ADR-010 asks for: "Major tracker or scoring
changes should be justified against labeled held-out clips ... rather than
tuned only to the four demo videos." Until now `app.evaluation.metrics` was
implemented and tested but called by nothing, so every threshold in
`app/behavior/scoring.py` was justified by demo impressions alone.

Usage:
    python eval/run_eval.py                       # all labelled clips
    python eval/run_eval.py --tolerance 1.5
    python eval/run_eval.py --clip warehouse-fall

Read docs/EVALUATION_RESULTS.md before quoting any number from this.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import AnalysisRequest, pipeline_config_from_env  # noqa: E402
from app.evaluation.metrics import EvaluationEvent, evaluate_events  # noqa: E402
from app.pipeline.video_pipeline import analyze_video  # noqa: E402

LABELS_DIR = Path(__file__).parent / "labels"

# Severities that assert something is wrong. A false positive here is the
# expensive kind: it is what a reviewer would be paged about.
ALERTING_SEVERITIES = {"high", "review_needed", "medium"}


def load_labels(clip_filter: str | None) -> list[dict]:
    labels = []
    for path in sorted(LABELS_DIR.glob("*.json")):
        if clip_filter and clip_filter not in path.stem:
            continue
        labels.append(json.loads(path.read_text()))
    return labels


def run_clip(clip_path: Path, output_path: Path) -> dict:
    request = AnalysisRequest(
        video_path=clip_path,
        output_path=output_path,
        config=pipeline_config_from_env(),
    )
    return analyze_video(request)


def predictions_from(result: dict) -> list[EvaluationEvent]:
    events = result.get("events") or []
    return [
        EvaluationEvent(
            event_type=str(event.get("event_type", "")),
            track_id=int(event.get("track_id", 0) or 0),
            timestamp_s=float(event.get("timestamp_s", 0.0) or 0.0),
        )
        for event in events
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tolerance", type=float, default=1.5, help="Temporal tolerance (s).")
    parser.add_argument("--clip", default=None, help="Substring filter on clip name.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    labels = load_labels(args.clip)
    if not labels:
        print("no labelled clips found", file=sys.stderr)
        return 1

    all_truth: list[EvaluationEvent] = []
    all_predictions: list[EvaluationEvent] = []
    total_duration = 0.0
    rows: list[dict] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for label in labels:
            clip_path = BACKEND_ROOT / label["clip"]
            if not clip_path.exists():
                print(f"SKIP {label['clip']} (missing)", file=sys.stderr)
                continue

            result = run_clip(clip_path, Path(tmpdir) / f"{clip_path.stem}.json")
            predictions = predictions_from(result)
            truth = [
                EvaluationEvent(
                    event_type=event["event_type"],
                    track_id=int(event.get("track_id", 0)),
                    timestamp_s=float(event["timestamp_s"]),
                )
                for event in label["events"]
            ]

            duration = float(label["duration_s"])
            metrics = evaluate_events(
                truth,
                # Only compare against the event types this clip is labelled
                # for. The pipeline also emits informational rows (slow
                # walking, uncertainty) that the labels make no claim about,
                # and counting those as false positives would be dishonest in
                # the other direction.
                [p for p in predictions if p.event_type in {t.event_type for t in truth}]
                if truth
                else [],
                duration_s=duration,
                tolerance_s=args.tolerance,
                require_track_match=False,
            )

            alerting = [
                event
                for event in (result.get("events") or [])
                if event.get("severity") in ALERTING_SEVERITIES
            ]
            fall_events = [
                event
                for event in (result.get("events") or [])
                if event.get("event_type") == "Fall-like motion event"
            ]

            rows.append(
                {
                    "clip": clip_path.name,
                    "positive": label["positive"],
                    "metrics": metrics.to_dict(),
                    "alerting_event_count": len(alerting),
                    "fall_event_count": len(fall_events),
                    "scene_reliability": result.get("scene_reliability"),
                    "qualified_subject_count": result.get("qualified_subject_count"),
                }
            )

            all_truth.extend(truth)
            all_predictions.extend(
                p for p in predictions if p.event_type in {t.event_type for t in truth}
            )
            total_duration += duration

    aggregate = evaluate_events(
        all_truth,
        all_predictions,
        duration_s=max(total_duration, 1e-6),
        tolerance_s=args.tolerance,
        require_track_match=False,
    )

    if args.json:
        print(json.dumps({"clips": rows, "aggregate": aggregate.to_dict()}, indent=2))
        return 0

    print(f"\nEvent-level evaluation · tolerance ±{args.tolerance}s · {len(rows)} clips\n")
    print(f"{'clip':<28} {'label':<9} {'TP':>3} {'FP':>3} {'FN':>3} {'alerting':>9} {'falls':>6}")
    print("-" * 72)
    for row in rows:
        m = row["metrics"]
        kind = "positive" if row["positive"] else "NEGATIVE"
        print(
            f"{row['clip']:<28} {kind:<9} {m['true_positives']:>3} {m['false_positives']:>3} "
            f"{m['false_negatives']:>3} {row['alerting_event_count']:>9} {row['fall_event_count']:>6}"
        )

    print("\nAggregate over labelled event types:")
    print(f"  precision                 {aggregate.precision:.2f}")
    print(f"  recall                    {aggregate.recall:.2f}")
    print(f"  f1                        {aggregate.f1:.2f}")
    print(f"  false alarms / minute     {aggregate.false_alarms_per_minute:.2f}")
    timing = aggregate.mean_absolute_timing_error_s
    print(f"  mean timing error         {f'{timing:.2f}s' if timing is not None else 'n/a'}")

    negatives = [row for row in rows if not row["positive"]]
    false_alarm_clips = [row for row in negatives if row["fall_event_count"] > 0]
    print("\nNegative-control check (clips with no fall in them):")
    print(f"  clips                     {len(negatives)}")
    print(f"  with a fall event         {len(false_alarm_clips)}  <- should be 0")

    print(
        "\nThese are engineering metrics on 4 hand-labelled clips. That is not a"
        "\nvalidation set and establishes nothing about clinical validity."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
