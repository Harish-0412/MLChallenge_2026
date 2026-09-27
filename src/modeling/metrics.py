"""Official query-macro F0.5 metric with strict input validation."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .contracts import S1_RE, TARGET_RE


class MetricInputError(ValueError):
    """Metric input is malformed or incomplete."""


@dataclass(frozen=True, slots=True)
class F05Result:
    macro_f05: float
    query_count: int
    perfect_queries: int
    singleton_count: int
    singleton_false_positives: int


def _validated_set(owner: str, values: Iterable[str], label: str) -> set[str]:
    raw = list(values)
    if len(raw) != len(set(raw)):
        raise MetricInputError(f"{label} contains duplicates for {owner}")
    invalid = [value for value in raw if not TARGET_RE.fullmatch(value)]
    if invalid:
        raise MetricInputError(f"{label} contains invalid target IDs for {owner}: {invalid[:3]}")
    return set(raw)


def f05_for_sets(truth: set[str], prediction: set[str]) -> float:
    if not truth:
        return 1.0 if not prediction else 0.0
    tp = len(truth & prediction)
    fp = len(prediction - truth)
    fn = len(truth - prediction)
    denominator = 1.25 * tp + fp + 0.25 * fn
    return 0.0 if denominator == 0 else (1.25 * tp) / denominator


def score_f05(
    truth: Mapping[str, Iterable[str]],
    predictions: Mapping[str, Iterable[str]],
    *,
    required_s1_ids: Iterable[str] | None = None,
) -> F05Result:
    required = set(required_s1_ids if required_s1_ids is not None else truth)
    if any(not S1_RE.fullmatch(value) for value in required):
        raise MetricInputError("required_s1_ids contains an invalid Source-1 ID")
    if set(truth) != required:
        missing, extra = required - set(truth), set(truth) - required
        raise MetricInputError(f"truth S1 coverage mismatch; missing={sorted(missing)[:3]}, extra={sorted(extra)[:3]}")
    if set(predictions) != required:
        missing, extra = required - set(predictions), set(predictions) - required
        raise MetricInputError(f"prediction S1 coverage mismatch; missing={sorted(missing)[:3]}, extra={sorted(extra)[:3]}")
    if not required:
        raise MetricInputError("cannot score an empty query set")

    total = perfect = singletons = singleton_fp = 0
    for s1_id in sorted(required):
        true_set = _validated_set(s1_id, truth[s1_id], "truth")
        pred_set = _validated_set(s1_id, predictions[s1_id], "prediction")
        value = f05_for_sets(true_set, pred_set)
        total += value
        perfect += int(value == 1.0)
        if not true_set:
            singletons += 1
            singleton_fp += int(bool(pred_set))
    return F05Result(total / len(required), len(required), perfect, singletons, singleton_fp)


def macro_f05(
    truth: Mapping[str, Iterable[str]], predictions: Mapping[str, Iterable[str]], *, required_s1_ids: Iterable[str] | None = None
) -> float:
    return score_f05(truth, predictions, required_s1_ids=required_s1_ids).macro_f05

