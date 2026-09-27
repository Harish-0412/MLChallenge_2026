#!/usr/bin/env python3
"""Generate deterministic, labeled cloud smoke inputs without Member B artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cleaning import record  # noqa: E402
from modeling.contracts import CandidateRecord, table_from_candidates  # noqa: E402
from normalization import comparison_key  # noqa: E402

COUNTS = {"train": 40, "early-stop": 20, "calibration": 20, "holdout": 20, "test": 20}


def feature_row(entity_id, name, address, source):
    return record.build_row(entity_id, name, address, "India", comparison_key(name), comparison_key(address),
                            "train" if source else "test", int(entity_id[1]), "feat_smoke", "hyg_smoke")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="tmp/sagemaker-sample")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    root = ROOT / args.output
    if root.exists():
        if not args.replace:
            raise FileExistsError(f"refusing to overwrite {root}; pass --replace for this disposable tmp path")
        if ROOT not in root.resolve().parents or root.name != "sagemaker-sample":
            raise ValueError("unsafe sample replacement path")
        shutil.rmtree(root)
    (root / "features" / "feat_v2_0").mkdir(parents=True)
    feature_rows, next_id = [], 1
    labels = {}
    for partition, count in COUNTS.items():
        candidate_dir = root / "candidates" / "candidate_v1" / partition
        candidate_dir.mkdir(parents=True)
        candidates, truth, slices = [], {}, {}
        for local_index in range(count):
            query_number, next_id = next_id, next_id + 1
            query_id = f"S1-{query_number:09d}"
            positive_id = f"S2-{query_number:09d}"
            negative_id = f"S3-{query_number:09d}"
            singleton = local_index % 5 == 0
            feature_rows.append(feature_row(query_id, f"Acme Clinic {query_number}", f"{query_number} Lake Road Karnataka", 1))
            feature_rows.append(feature_row(positive_id, f"ACME CLINIC {query_number} PRIVATE LIMITED",
                                            f"{query_number} Lake Rd Karnataka", 2))
            feature_rows.append(feature_row(negative_id, f"Unrelated Market {query_number}",
                                            f"{query_number + 9000} Hill Street Karnataka", 3))
            label = -1 if partition == "test" else 0
            if not singleton:
                candidates.append(CandidateRecord(
                    query_id, positive_id, "India", retrieval_channels=("name", "address"),
                    retrieval_scores=(.99, .95), retrieval_ranks=(1, 1), candidate_block_size=2,
                    query_candidate_count=2, evidence_slice="strong", is_positive=-1 if partition == "test" else 1,
                ))
            candidates.append(CandidateRecord(
                query_id, negative_id, "India", retrieval_channels=("fallback",), retrieval_scores=(.15,),
                retrieval_ranks=(2,), candidate_block_size=20, query_candidate_count=2,
                evidence_slice="weak", is_positive=label,
            ))
            truth[query_id] = [] if singleton else [positive_id]
            slices[query_id] = ["India", "singleton" if singleton else "non_singleton"]
        pq.write_table(table_from_candidates(candidates), candidate_dir / "candidates.parquet", compression="zstd")
        labels[partition] = (truth, slices)

    table = pa.Table.from_pylist([dict(zip(record.COLUMNS, row)) for row in feature_rows], schema=record.SCHEMA)
    pq.write_table(table, root / "features" / "feat_v2_0" / "records.parquet", compression="zstd")
    metrics_dir = root / "candidate-metrics" / "candidate_v1"
    metrics_dir.mkdir(parents=True)
    (metrics_dir / "metrics.json").write_text(
        json.dumps({"candidate_recall": 1.0, "candidate_oracle_f05": 1.0}, indent=2) + "\n", encoding="utf-8"
    )
    label_root = root / "labels" / "fold_v1"
    (label_root / "calibration").mkdir(parents=True)
    (label_root / "calibration" / "truth.json").write_text(json.dumps(labels["calibration"][0], sort_keys=True), encoding="utf-8")
    for name, data in (("truth", labels["holdout"][0]), ("slices", labels["holdout"][1])):
        path = label_root / "holdout" / name
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{name}.json").write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    required = label_root / "test" / "required"
    required.mkdir(parents=True)
    (required / "required.json").write_text(json.dumps(sorted(labels["test"][0])), encoding="utf-8")
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

