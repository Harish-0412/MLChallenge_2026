"""Deterministic query-level decision policy and macro-F0.5 policy search."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Iterable, Mapping, Sequence

from .contracts import QueryDecision, ScoredPair
from .metrics import macro_f05


@dataclass(frozen=True, order=True, slots=True)
class DecisionPolicy:
    threshold: float = 0.5
    top_k: int = 5
    min_top_margin: float = 0.0
    max_cardinality: int = 5
    slice_thresholds: tuple[tuple[str, float], ...] = ()
    version: str = "policy_v1"

    def __post_init__(self) -> None:
        if not 0 <= self.threshold <= 1 or self.top_k < 1 or self.max_cardinality < 1 or self.min_top_margin < 0:
            raise ValueError("invalid decision-policy bounds")
        for _, value in self.slice_thresholds:
            if not 0 <= value <= 1:
                raise ValueError("slice threshold must be in [0, 1]")

    def threshold_for(self, evidence_slice: str) -> float:
        return dict(self.slice_thresholds).get(evidence_slice, self.threshold)


def decide_queries(scored_pairs: Iterable[ScoredPair], required_s1_ids: Iterable[str], policy: DecisionPolicy) -> list[QueryDecision]:
    grouped: dict[str, list[ScoredPair]] = {s1_id: [] for s1_id in required_s1_ids}
    for pair in scored_pairs:
        pair.validate()
        if pair.s1_entity_id not in grouped:
            raise ValueError(f"scored pair belongs to an unknown query: {pair.s1_entity_id}")
        grouped[pair.s1_entity_id].append(pair)

    decisions = []
    for s1_id in sorted(grouped):
        ranked = sorted(grouped[s1_id], key=lambda pair: (-pair.score, pair.candidate_entity_id))
        selected: tuple[str, ...] = ()
        if ranked:
            second_score = ranked[1].score if len(ranked) > 1 else 0.0
            if ranked[0].score - second_score >= policy.min_top_margin:
                eligible = [pair for pair in ranked if pair.score >= policy.threshold_for(pair.evidence_slice)]
                cap = min(policy.top_k, policy.max_cardinality)
                selected = tuple(pair.candidate_entity_id for pair in eligible[:cap])
        decision = QueryDecision(s1_id, selected, policy.version)
        decision.validate()
        decisions.append(decision)
    return decisions


def search_policy(
    scored_pairs: Sequence[ScoredPair],
    truth: Mapping[str, Iterable[str]],
    *,
    thresholds: Sequence[float],
    top_ks: Sequence[int],
    margins: Sequence[float] = (0.0,),
    max_cardinalities: Sequence[int] = (5,),
) -> tuple[DecisionPolicy, float]:
    best_policy: DecisionPolicy | None = None
    best_score = -1.0
    required = tuple(sorted(truth))
    for threshold, top_k, margin, cap in product(sorted(set(thresholds)), sorted(set(top_ks)), sorted(set(margins)), sorted(set(max_cardinalities))):
        policy = DecisionPolicy(threshold, top_k, margin, cap)
        decisions = decide_queries(scored_pairs, required, policy)
        predictions = {decision.s1_entity_id: decision.matched_entity_ids for decision in decisions}
        score = macro_f05(truth, predictions, required_s1_ids=required)
        # Stable preference on a tie: stricter threshold, smaller cap, larger margin.
        tie_key = (policy.threshold, -policy.top_k, policy.min_top_margin, -policy.max_cardinality)
        current_key = (-1.0, 0, 0.0, 0) if best_policy is None else (
            best_policy.threshold, -best_policy.top_k, best_policy.min_top_margin, -best_policy.max_cardinality
        )
        if score > best_score or (score == best_score and tie_key > current_key):
            best_policy, best_score = policy, score
    if best_policy is None:
        raise ValueError("policy search grid is empty")
    return best_policy, best_score

