"""Streaming pair-feature generation from the versioned record and candidate contracts."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from rapidfuzz import fuzz

from .contracts import CANDIDATE_SCHEMA, ContractError, PAIR_CONTRACT_VERSION, validate_candidate_table
from .reproducibility import sha256_file


METADATA_COLUMNS = (
    "s1_entity_id", "candidate_entity_id", "country", "evidence_slice", "is_positive", "sample_weight",
)

# This is the only set of columns a learned estimator may receive.
FEATURE_COLUMNS = (
    "name_key_equal", "name_hyg_ratio", "name_hyg_token_set_ratio", "name_core_ratio",
    "name_core_token_jaccard", "name_core_char3_dice", "name_core_compact_equal",
    "name_accent_ratio", "name_translit_ratio", "name_skeleton_ratio", "legal_form_equal",
    "legal_form_both_present", "name_informative_min", "name_same_script", "name_cross_script",
    "name_placeholder_any", "name_domain_any", "address_missing_any", "address_missing_both",
    "address_canon_ratio", "address_token_jaccard", "address_char3_dice", "address_segment_jaccard",
    "address_state_equal", "address_state_both_present", "address_state_conflict_any",
    "address_city_overlap", "address_postal_overlap", "address_number_jaccard", "address_number_shared",
    "address_number_conflicts", "address_number_context_jaccard", "address_parse_conf_min",
    "quality_issue_count", "retrieval_channel_count", "retrieval_score_max", "retrieval_rank_best",
    "candidate_block_size", "query_candidate_count",
)

FORBIDDEN_MODEL_COLUMNS = frozenset({
    "entity_id", "id_num", "source", "split", "fold", "fold_id", "country", "s1_entity_id",
    "candidate_entity_id", "is_positive", "label", "truth_cardinality", "true_match_count",
    "injected_positive", "sample_weight", "candidate_version", "feature_version", "hygiene_version",
})

PAIR_SCHEMA = pa.schema(
    [
        pa.field("s1_entity_id", pa.string(), nullable=False),
        pa.field("candidate_entity_id", pa.string(), nullable=False),
        pa.field("country", pa.string(), nullable=False),
        pa.field("evidence_slice", pa.string(), nullable=False),
        pa.field("is_positive", pa.int8(), nullable=False),
        pa.field("sample_weight", pa.float32(), nullable=False),
    ]
    + [pa.field(name, pa.float32(), nullable=False) for name in FEATURE_COLUMNS]
)

_RECORD_FIELDS = (
    "name_key", "name_hyg", "name_core", "name_core_compact", "name_latin_accent_key", "name_translit",
    "name_skeleton", "legal_form", "name_ninformative", "name_scripts", "name_placeholder_like",
    "name_is_domain_like", "name_has_control", "name_has_format", "name_mojibake", "address_missing",
    "address_canon", "address_tokset", "address_segments", "address_state_canon", "address_state_conf",
    "address_city_candidates", "address_postal_candidates", "address_numbers_canon", "address_number_ctx",
    "address_parse_conf", "address_has_control", "address_has_format", "address_mojibake",
)


def assert_safe_feature_columns(columns: Iterable[str]) -> tuple[str, ...]:
    requested = tuple(columns)
    unknown = set(requested) - set(FEATURE_COLUMNS)
    forbidden = set(requested) & FORBIDDEN_MODEL_COLUMNS
    if unknown or forbidden:
        raise ContractError(f"unsafe model feature selection; unknown={sorted(unknown)}, forbidden={sorted(forbidden)}")
    if len(set(requested)) != len(requested):
        raise ContractError("model feature list contains duplicates")
    return requested


def _tokens(value: str) -> set[str]:
    return {token for token in value.split() if token}


def _jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _char_dice(left: str, right: str, n: int = 3) -> float:
    def grams(value: str) -> set[str]:
        padded = f"  {value}  "
        return {padded[i:i + n] for i in range(max(0, len(padded) - n + 1))}
    a, b = grams(left), grams(right)
    return 1.0 if not a and not b else (2.0 * len(a & b)) / (len(a) + len(b))


def _ratio(left: str, right: str) -> float:
    return float(fuzz.ratio(left, right)) / 100.0


def _token_set_ratio(left: str, right: str) -> float:
    return float(fuzz.token_set_ratio(left, right)) / 100.0


_CONFIDENCE = {"missing": 0.0, "low": 1.0 / 3.0, "medium": 2.0 / 3.0, "high": 1.0}


def compute_pair_features(query: Mapping[str, Any], target: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, float]:
    if query["country"] != target["country"] or query["country"] != candidate["country"]:
        raise ContractError("candidate/query/target country mismatch")
    q_nums, t_nums = set(query["address_numbers_canon"]), set(target["address_numbers_canon"])
    shared_nums = q_nums & t_nums
    both_numbers = bool(q_nums and t_nums)
    quality_fields = ("name_has_control", "name_has_format", "name_mojibake", "address_has_control", "address_has_format", "address_mojibake")
    channels = candidate["retrieval_channels"]
    scores = candidate["retrieval_scores"]
    ranks = candidate["retrieval_ranks"]
    return {
        "name_key_equal": float(bool(query["name_key"]) and query["name_key"] == target["name_key"]),
        "name_hyg_ratio": _ratio(query["name_hyg"], target["name_hyg"]),
        "name_hyg_token_set_ratio": _token_set_ratio(query["name_hyg"], target["name_hyg"]),
        "name_core_ratio": _ratio(query["name_core"], target["name_core"]),
        "name_core_token_jaccard": _jaccard(_tokens(query["name_core"]), _tokens(target["name_core"])),
        "name_core_char3_dice": _char_dice(query["name_core"], target["name_core"]),
        "name_core_compact_equal": float(bool(query["name_core_compact"]) and query["name_core_compact"] == target["name_core_compact"]),
        "name_accent_ratio": _ratio(query["name_latin_accent_key"], target["name_latin_accent_key"]),
        "name_translit_ratio": _ratio(query["name_translit"], target["name_translit"]),
        "name_skeleton_ratio": _ratio(query["name_skeleton"], target["name_skeleton"]),
        "legal_form_equal": float(bool(query["legal_form"]) and query["legal_form"] == target["legal_form"]),
        "legal_form_both_present": float(bool(query["legal_form"] and target["legal_form"])),
        "name_informative_min": float(min(query["name_ninformative"], target["name_ninformative"])),
        "name_same_script": float(query["name_scripts"] == target["name_scripts"]),
        "name_cross_script": float(bool(query["name_scripts"] and target["name_scripts"] and not (query["name_scripts"] & target["name_scripts"]))),
        "name_placeholder_any": float(query["name_placeholder_like"] or target["name_placeholder_like"]),
        "name_domain_any": float(query["name_is_domain_like"] or target["name_is_domain_like"]),
        "address_missing_any": float(query["address_missing"] or target["address_missing"]),
        "address_missing_both": float(query["address_missing"] and target["address_missing"]),
        "address_canon_ratio": _ratio(query["address_canon"], target["address_canon"]),
        "address_token_jaccard": _jaccard(_tokens(query["address_tokset"]), _tokens(target["address_tokset"])),
        "address_char3_dice": _char_dice(query["address_canon"], target["address_canon"]),
        "address_segment_jaccard": _jaccard(query["address_segments"], target["address_segments"]),
        "address_state_equal": float(bool(query["address_state_canon"]) and query["address_state_canon"] == target["address_state_canon"]),
        "address_state_both_present": float(bool(query["address_state_canon"] and target["address_state_canon"])),
        "address_state_conflict_any": float(query["address_state_conf"] == "conflict" or target["address_state_conf"] == "conflict"),
        "address_city_overlap": float(bool(set(query["address_city_candidates"]) & set(target["address_city_candidates"]))),
        "address_postal_overlap": float(bool(set(query["address_postal_candidates"]) & set(target["address_postal_candidates"]))),
        "address_number_jaccard": _jaccard(q_nums, t_nums),
        "address_number_shared": float(len(shared_nums)),
        "address_number_conflicts": float(len((q_nums | t_nums) - shared_nums) if both_numbers else 0),
        "address_number_context_jaccard": _jaccard(query["address_number_ctx"], target["address_number_ctx"]),
        "address_parse_conf_min": min(_CONFIDENCE.get(query["address_parse_conf"], 0.0), _CONFIDENCE.get(target["address_parse_conf"], 0.0)),
        "quality_issue_count": float(sum(bool(query[name]) + bool(target[name]) for name in quality_fields)),
        "retrieval_channel_count": float(len(channels)),
        "retrieval_score_max": float(max(scores, default=0.0)),
        "retrieval_rank_best": float(min(ranks, default=0)),
        "candidate_block_size": float(candidate["candidate_block_size"]),
        "query_candidate_count": float(candidate["query_candidate_count"]),
    }


def _record_from_join(row: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    result = {name: row[f"{prefix}_{name}"] for name in _RECORD_FIELDS}
    result["country"] = row[f"{prefix}_country"]
    return result


def _sql_path(path: Path) -> str:
    return str(path).replace("'", "''").replace("\\", "/")


def build_pair_table(
    feature_root: str | Path,
    candidate_path: str | Path,
    output_path: str | Path,
    *,
    batch_size: int = 50_000,
    threads: int = 4,
    validate: bool = True,
) -> dict[str, Any]:
    """Join candidates to record features and stream deterministic pair features to Parquet.

    ``validate`` runs the full per-row contract check (``validate_candidate_table``), which is a pure-Python loop and the dominant cost at large
    scale (tens of millions of rows). Callers that already produced the candidate table through a schema-conforming, tested path (for example
    ``ranking.pairs.aggregate_candidates`` followed by its own schema cast) may pass ``validate=False`` to skip it; the row count and dtypes are
    still checked structurally below regardless.
    """
    feature_root, candidate_path, output_path = Path(feature_root), Path(candidate_path), Path(output_path)
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite pair table: {output_path}")
    candidate_table = pq.read_table(candidate_path)
    if validate:
        validate_candidate_table(candidate_table)
    elif candidate_table.schema != CANDIDATE_SCHEMA:
        raise ContractError(f"candidate schema mismatch:\nexpected {CANDIDATE_SCHEMA}\nactual {candidate_table.schema}")
    feature_glob = feature_root / "**" / "*.parquet"
    if not list(feature_root.rglob("*.parquet")):
        raise FileNotFoundError(f"no feature Parquet files below {feature_root}")

    selects = []
    for prefix, alias in (("q", "q"), ("t", "t")):
        selects.append(f"{alias}.country AS {prefix}_country")
        selects.extend(f"{alias}.{name} AS {prefix}_{name}" for name in _RECORD_FIELDS)
    sql = f"""
        SELECT c.*, {', '.join(selects)}
        FROM read_parquet('{_sql_path(candidate_path)}') c
        JOIN read_parquet('{_sql_path(feature_glob)}', hive_partitioning=false) q ON q.entity_id = c.s1_entity_id
        JOIN read_parquet('{_sql_path(feature_glob)}', hive_partitioning=false) t ON t.entity_id = c.candidate_entity_id
        ORDER BY c.s1_entity_id, c.candidate_entity_id
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="pair_build_", dir=output_path.parent))
    tmp_path = tmp_dir / output_path.name
    writer: pq.ParquetWriter | None = None
    row_count = 0
    try:
        con = duckdb.connect()
        con.execute(f"SET threads={int(threads)}")
        reader = con.execute(sql).fetch_record_batch(rows_per_batch=batch_size)
        writer = pq.ParquetWriter(tmp_path, PAIR_SCHEMA, compression="zstd", use_dictionary=True)
        for batch in reader:
            output_rows = []
            for row in batch.to_pylist():
                query, target = _record_from_join(row, "q"), _record_from_join(row, "t")
                features = compute_pair_features(query, target, row)
                output_rows.append({
                    "s1_entity_id": row["s1_entity_id"], "candidate_entity_id": row["candidate_entity_id"],
                    "country": row["country"], "evidence_slice": row["evidence_slice"],
                    "is_positive": row["is_positive"], "sample_weight": row["sample_weight"], **features,
                })
            table = pa.Table.from_pylist(output_rows, schema=PAIR_SCHEMA)
            writer.write_table(table)
            row_count += table.num_rows
        writer.close()
        writer = None
        if row_count != candidate_table.num_rows:
            raise ContractError(f"feature join lost or duplicated pairs: candidates={candidate_table.num_rows}, output={row_count}")
        tmp_path.replace(output_path)
    finally:
        if writer is not None:
            writer.close()
        shutil.rmtree(tmp_dir, ignore_errors=True)

    manifest = {
        "contract_version": PAIR_CONTRACT_VERSION,
        "candidate_rows": candidate_table.num_rows,
        "pair_rows": row_count,
        "feature_columns": list(FEATURE_COLUMNS),
        "schema": str(PAIR_SCHEMA),
        "candidate_sha256": sha256_file(candidate_path),
        "output_sha256": sha256_file(output_path),
        "batch_size": batch_size,
    }
    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return manifest


def feature_matrix(table: pa.Table, columns: Iterable[str] = FEATURE_COLUMNS):
    """Return a float32 matrix after enforcing the model-feature allowlist."""
    import numpy as np

    selected = assert_safe_feature_columns(columns)
    missing = set(selected) - set(table.column_names)
    if missing:
        raise ContractError(f"pair table is missing model features: {sorted(missing)}")
    return np.column_stack([table[name].to_numpy(zero_copy_only=False) for name in selected]).astype("float32", copy=False)

