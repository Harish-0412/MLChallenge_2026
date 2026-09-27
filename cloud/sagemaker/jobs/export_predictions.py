#!/usr/bin/env python3
"""SageMaker Processing entry point for calibrated inference and strict TSV export."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib

from modeling.decision import DecisionPolicy, decide_queries
from modeling.export import export_submission
from modeling.inference import score_pair_table
from common import read_json, read_parquet_tree, safe_extract_model


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="/opt/ml/processing/input/model")
    parser.add_argument("--pairs", default="/opt/ml/processing/input/pairs")
    parser.add_argument("--required", default="/opt/ml/processing/input/required")
    parser.add_argument("--output", default="/opt/ml/processing/output/submission")
    args = parser.parse_args()
    unpacked = safe_extract_model(args.model, "/tmp/model")
    model, calibrator = joblib.load(unpacked / "model.joblib"), joblib.load(unpacked / "calibrator.joblib")
    raw_policy = json.loads((unpacked / "policy.json").read_text(encoding="utf-8"))
    raw_policy["slice_thresholds"] = tuple(tuple(item) for item in raw_policy.get("slice_thresholds", ()))
    policy = DecisionPolicy(**raw_policy)
    pairs = read_parquet_tree(args.pairs)
    required = tuple(read_json(args.required))
    scored = score_pair_table(pairs, model, calibrator)
    decisions = decide_queries(scored, required, policy)
    candidates = {query_id: [] for query_id in required}
    for pair in scored:
        candidates[pair.s1_entity_id].append(pair.candidate_entity_id)
    export_submission(decisions, candidates, required, Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

