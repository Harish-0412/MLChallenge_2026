"""Deterministic, weighted hard-negative sampling."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from typing import Any, Iterable, Mapping


def _stable_rank(seed: int, query_id: str, candidate_id: str) -> bytes:
    return hashlib.sha256(f"{seed}\0{query_id}\0{candidate_id}".encode("utf-8")).digest()


def sample_training_pairs(
    rows: Iterable[Mapping[str, Any]], *, negatives_per_positive: int = 10, minimum_negatives: int = 5, seed: int = 20260926
) -> list[dict[str, Any]]:
    """Keep all positives and sample negatives per query, stratified by evidence_slice.

    Selected negatives receive inverse sampling-fraction weights within their
    query/stratum. Retrieval misses must never be included in ``rows`` as negatives.
    """
    if negatives_per_positive < 0 or minimum_negatives < 0:
        raise ValueError("negative sampling limits must be non-negative")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for source in rows:
        row = dict(source)
        key = (row["s1_entity_id"], row["candidate_entity_id"])
        if key in seen:
            raise ValueError(f"duplicate pair in sampler: {key}")
        seen.add(key)
        if row["is_positive"] not in (0, 1):
            raise ValueError("training sampler requires binary is_positive labels")
        grouped[row["s1_entity_id"]].append(row)

    output: list[dict[str, Any]] = []
    for query_id in sorted(grouped):
        query_rows = grouped[query_id]
        positives = [row for row in query_rows if row["is_positive"] == 1]
        negatives = [row for row in query_rows if row["is_positive"] == 0]
        budget = min(len(negatives), max(minimum_negatives, negatives_per_positive * len(positives)))
        by_slice: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in negatives:
            by_slice[row.get("evidence_slice", "default")].append(row)

        selected: list[dict[str, Any]] = []
        # Round-robin across strata prevents a large easy stratum from consuming the budget.
        ranked = {
            name: sorted(items, key=lambda row: _stable_rank(seed, query_id, row["candidate_entity_id"]))
            for name, items in by_slice.items()
        }
        positions = Counter()
        slice_names = sorted(ranked)
        while len(selected) < budget and slice_names:
            remaining = []
            for name in slice_names:
                index = positions[name]
                if index < len(ranked[name]) and len(selected) < budget:
                    selected.append(ranked[name][index])
                    positions[name] += 1
                if positions[name] < len(ranked[name]):
                    remaining.append(name)
            slice_names = remaining

        chosen_counts = Counter(row.get("evidence_slice", "default") for row in selected)
        total_counts = Counter(row.get("evidence_slice", "default") for row in negatives)
        for row in positives:
            copied = dict(row)
            copied["sample_weight"] = float(copied.get("sample_weight", 1.0))
            output.append(copied)
        for row in selected:
            copied = dict(row)
            name = copied.get("evidence_slice", "default")
            copied["sample_weight"] = float(total_counts[name] / chosen_counts[name])
            output.append(copied)
    return sorted(output, key=lambda row: (row["s1_entity_id"], -row["is_positive"], row["candidate_entity_id"]))

