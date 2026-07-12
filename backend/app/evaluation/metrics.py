"""Event-level benchmark metrics for labeled mobility-review clips."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite


@dataclass(frozen=True)
class EvaluationEvent:
    """A minimal event annotation shared by labels and predictions."""

    event_type: str
    track_id: int
    timestamp_s: float


@dataclass(frozen=True)
class EventMetrics:
    """Transparent event-detection metrics for one clip or aggregate stream."""

    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    false_alarms_per_minute: float
    mean_absolute_timing_error_s: float | None
    duration_s: float
    tolerance_s: float

    def to_dict(self) -> dict[str, float | int | None]:
        return asdict(self)


def evaluate_events(
    ground_truth: list[EvaluationEvent],
    predictions: list[EvaluationEvent],
    *,
    duration_s: float,
    tolerance_s: float = 1.0,
) -> EventMetrics:
    """Match events one-to-one by type, subject, and nearest timestamp.

    This is an engineering benchmark, not a clinical validation metric. A
    prediction can match at most one label and vice versa.
    """

    if not isfinite(duration_s) or duration_s <= 0.0:
        raise ValueError("duration_s must be finite and greater than zero")
    if not isfinite(tolerance_s) or tolerance_s < 0.0:
        raise ValueError("tolerance_s must be finite and non-negative")

    unmatched_predictions = set(range(len(predictions)))
    timing_errors: list[float] = []

    for label in sorted(ground_truth, key=lambda item: item.timestamp_s):
        candidates = [
            (abs(predictions[index].timestamp_s - label.timestamp_s), index)
            for index in unmatched_predictions
            if predictions[index].event_type == label.event_type
            and predictions[index].track_id == label.track_id
            and abs(predictions[index].timestamp_s - label.timestamp_s) <= tolerance_s
        ]
        if not candidates:
            continue
        timing_error, prediction_index = min(candidates)
        unmatched_predictions.remove(prediction_index)
        timing_errors.append(timing_error)

    true_positives = len(timing_errors)
    false_positives = len(predictions) - true_positives
    false_negatives = len(ground_truth) - true_positives
    precision = _safe_rate(true_positives, true_positives + false_positives)
    recall = _safe_rate(true_positives, true_positives + false_negatives)
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if precision + recall > 0.0
        else 0.0
    )
    return EventMetrics(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1=f1,
        false_alarms_per_minute=false_positives / (duration_s / 60.0),
        mean_absolute_timing_error_s=(
            sum(timing_errors) / len(timing_errors) if timing_errors else None
        ),
        duration_s=duration_s,
        tolerance_s=tolerance_s,
    )


def _safe_rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0
