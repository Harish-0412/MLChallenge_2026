"""Strict, deterministic challenge TSV export."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from .contracts import QueryDecision, S1_RE, TARGET_RE


def _validate_mapping(values: Mapping[str, Iterable[str]], required: set[str], label: str) -> dict[str, tuple[str, ...]]:
    if set(values) != required:
        raise ValueError(f"{label} query coverage mismatch")
    result = {}
    for s1_id in sorted(required):
        raw = tuple(values[s1_id])
        if not S1_RE.fullmatch(s1_id) or any(not TARGET_RE.fullmatch(value) for value in raw):
            raise ValueError(f"{label} contains invalid IDs for {s1_id}")
        if len(raw) != len(set(raw)):
            raise ValueError(f"{label} contains duplicates for {s1_id}")
        result[s1_id] = tuple(sorted(raw))
    return result


def export_submission(
    decisions: Iterable[QueryDecision],
    candidates: Mapping[str, Iterable[str]],
    required_s1_ids: Iterable[str],
    output_dir: str | Path,
) -> tuple[Path, Path]:
    required = set(required_s1_ids)
    decision_map: dict[str, tuple[str, ...]] = {}
    for decision in decisions:
        decision.validate()
        if decision.s1_entity_id in decision_map:
            raise ValueError(f"duplicate query decision: {decision.s1_entity_id}")
        decision_map[decision.s1_entity_id] = decision.matched_entity_ids
    matched = _validate_mapping(decision_map, required, "decisions")
    candidate_map = _validate_mapping(candidates, required, "candidates")
    for s1_id in required:
        missing = set(matched[s1_id]) - set(candidate_map[s1_id])
        if missing:
            raise ValueError(f"final matches are absent from candidates for {s1_id}: {sorted(missing)[:3]}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    matching_path, candidate_path = output_dir / "matching_results.tsv", output_dir / "candidate_pairs.tsv"
    for path in (matching_path, candidate_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite submission artifact: {path}")
    with matching_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("source1_entity_id\tmatched_entity_ids\n")
        for s1_id in sorted(required):
            stream.write(f"{s1_id}\t{','.join(matched[s1_id])}\n")
    with candidate_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("source1_entity_id\tcandidate_entity_ids\n")
        for s1_id in sorted(required):
            stream.write(f"{s1_id}\t{','.join(candidate_map[s1_id])}\n")
    return matching_path, candidate_path

