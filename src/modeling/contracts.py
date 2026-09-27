"""Typed records and explicit Arrow contracts for the modeling pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Mapping, Sequence

import pyarrow as pa

S1_RE = re.compile(r"^S1-\d+$")
TARGET_RE = re.compile(r"^S[23]-\d+$")
CANDIDATE_CONTRACT_VERSION = "candidate_v1"
PAIR_CONTRACT_VERSION = "pair_v1"


class ContractError(ValueError):
    """Raised when an artifact violates its declared contract."""


CANDIDATE_SCHEMA = pa.schema([
    pa.field("s1_entity_id", pa.string(), nullable=False),
    pa.field("candidate_entity_id", pa.string(), nullable=False),
    pa.field("country", pa.string(), nullable=False),
    pa.field("candidate_version", pa.string(), nullable=False),
    pa.field("retrieval_channels", pa.list_(pa.string()), nullable=False),
    pa.field("retrieval_scores", pa.list_(pa.float32()), nullable=False),
    pa.field("retrieval_ranks", pa.list_(pa.int32()), nullable=False),
    pa.field("candidate_block_size", pa.int32(), nullable=False),
    pa.field("query_candidate_count", pa.int32(), nullable=False),
    pa.field("evidence_slice", pa.string(), nullable=False),
    pa.field("is_positive", pa.int8(), nullable=False),  # -1 at inference
    pa.field("sample_weight", pa.float32(), nullable=False),
])


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    s1_entity_id: str
    candidate_entity_id: str
    country: str
    candidate_version: str = CANDIDATE_CONTRACT_VERSION
    retrieval_channels: tuple[str, ...] = ()
    retrieval_scores: tuple[float, ...] = ()
    retrieval_ranks: tuple[int, ...] = ()
    candidate_block_size: int = 0
    query_candidate_count: int = 0
    evidence_slice: str = "default"
    is_positive: int = -1
    sample_weight: float = 1.0

    def validate(self) -> None:
        if not S1_RE.fullmatch(self.s1_entity_id):
            raise ContractError(f"invalid Source-1 ID: {self.s1_entity_id!r}")
        if not TARGET_RE.fullmatch(self.candidate_entity_id):
            raise ContractError(f"invalid candidate ID: {self.candidate_entity_id!r}")
        if not self.country:
            raise ContractError("country must be a non-empty open-set label")
        if self.is_positive not in (-1, 0, 1):
            raise ContractError("is_positive must be -1, 0, or 1")
        if self.sample_weight <= 0:
            raise ContractError("sample_weight must be positive")
        if len(self.retrieval_scores) not in (0, len(self.retrieval_channels)):
            raise ContractError("retrieval_scores must be empty or align with channels")
        if len(self.retrieval_ranks) not in (0, len(self.retrieval_channels)):
            raise ContractError("retrieval_ranks must be empty or align with channels")
        if len(set(self.retrieval_channels)) != len(self.retrieval_channels):
            raise ContractError("retrieval_channels must be unique")

    def as_arrow_dict(self) -> dict[str, Any]:
        self.validate()
        result = asdict(self)
        result["retrieval_channels"] = list(self.retrieval_channels)
        result["retrieval_scores"] = list(self.retrieval_scores)
        result["retrieval_ranks"] = list(self.retrieval_ranks)
        return result


@dataclass(frozen=True, slots=True)
class ScoredPair:
    s1_entity_id: str
    candidate_entity_id: str
    score: float
    country: str = ""
    evidence_slice: str = "default"

    def validate(self) -> None:
        if not S1_RE.fullmatch(self.s1_entity_id) or not TARGET_RE.fullmatch(self.candidate_entity_id):
            raise ContractError("scored pair contains an invalid entity ID")
        if not 0.0 <= self.score <= 1.0:
            raise ContractError("score must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class QueryDecision:
    s1_entity_id: str
    matched_entity_ids: tuple[str, ...]
    policy_version: str = "policy_v1"

    def validate(self) -> None:
        if not S1_RE.fullmatch(self.s1_entity_id):
            raise ContractError(f"invalid Source-1 ID: {self.s1_entity_id!r}")
        if len(set(self.matched_entity_ids)) != len(self.matched_entity_ids):
            raise ContractError("query decision contains duplicate matches")
        invalid = [value for value in self.matched_entity_ids if not TARGET_RE.fullmatch(value)]
        if invalid:
            raise ContractError(f"invalid target IDs: {invalid[:3]}")


@dataclass(slots=True)
class ExperimentReport:
    experiment_id: str
    source_revision: str
    feature_version: str
    candidate_version: str
    fold_version: str
    seed: int
    hyperparameters: dict[str, Any]
    runtime_seconds: float = 0.0
    peak_rss_bytes: int = 0
    metrics: dict[str, float] = field(default_factory=dict)
    slice_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    artifact_hashes: dict[str, str] = field(default_factory=dict)

    def to_mapping(self) -> Mapping[str, Any]:
        return asdict(self)


def table_from_candidates(records: Sequence[CandidateRecord]) -> pa.Table:
    rows = [record.as_arrow_dict() for record in records]
    return pa.Table.from_pylist(rows, schema=CANDIDATE_SCHEMA)


def validate_candidate_table(table: pa.Table) -> None:
    if table.schema != CANDIDATE_SCHEMA:
        raise ContractError(f"candidate schema mismatch:\nexpected {CANDIDATE_SCHEMA}\nactual {table.schema}")
    seen: set[tuple[str, str]] = set()
    for raw in table.to_pylist():
        record = CandidateRecord(
            **{**raw, "retrieval_channels": tuple(raw["retrieval_channels"]),
               "retrieval_scores": tuple(raw["retrieval_scores"]), "retrieval_ranks": tuple(raw["retrieval_ranks"])}
        )
        record.validate()
        key = (record.s1_entity_id, record.candidate_entity_id)
        if key in seen:
            raise ContractError(f"duplicate candidate pair: {key}")
        seen.add(key)

