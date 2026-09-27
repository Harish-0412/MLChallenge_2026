"""End-to-end overall and overlapping slice evaluation."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from .metrics import score_f05


def evaluate_slices(
    truth: Mapping[str, Iterable[str]],
    predictions: Mapping[str, Iterable[str]],
    query_slices: Mapping[str, Iterable[str]],
) -> dict[str, dict[str, Any]]:
    if set(query_slices) != set(truth):
        raise ValueError("query_slices coverage must exactly match truth")
    groups: dict[str, set[str]] = defaultdict(set)
    groups["all"] = set(truth)
    for query_id, labels in query_slices.items():
        for label in set(labels):
            groups[label].add(query_id)
    report = {}
    for label in sorted(groups):
        ids = groups[label]
        subset_truth = {query_id: truth[query_id] for query_id in ids}
        subset_predictions = {query_id: predictions[query_id] for query_id in ids}
        result = score_f05(subset_truth, subset_predictions, required_s1_ids=ids)
        report[label] = {
            "macro_f05": result.macro_f05,
            "queries": result.query_count,
            "perfect_queries": result.perfect_queries,
            "singletons": result.singleton_count,
            "singleton_false_positives": result.singleton_false_positives,
        }
    return report

