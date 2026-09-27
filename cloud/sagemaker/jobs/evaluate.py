#!/usr/bin/env python3
"""SageMaker Processing entry point for locked-fold end-to-end evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import joblib
import psutil

from cloud.sagemaker.metrics import emit_metrics
from modeling.decision import DecisionPolicy, decide_queries
from modeling.evaluation import evaluate_slices
from modeling.inference import score_pair_table
from common import read_json, read_parquet_tree, safe_extract_model


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="/opt/ml/processing/input/model")
    parser.add_argument("--pairs", default="/opt/ml/processing/input/pairs")
    parser.add_argument("--truth", default="/opt/ml/processing/input/truth")
    parser.add_argument("--slices", default="/opt/ml/processing/input/slices")
    parser.add_argument("--output", default="/opt/ml/processing/output/evaluation")
    parser.add_argument("--experiment-id", required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    unpacked = safe_extract_model(args.model, "/tmp/model")
    model, calibrator = joblib.load(unpacked / "model.joblib"), joblib.load(unpacked / "calibrator.joblib")
    raw_policy = json.loads((unpacked / "policy.json").read_text(encoding="utf-8"))
    raw_policy["slice_thresholds"] = tuple(tuple(item) for item in raw_policy.get("slice_thresholds", ()))
    policy = DecisionPolicy(**raw_policy)
    pairs = read_parquet_tree(args.pairs)
    truth = {key: tuple(value) for key, value in read_json(args.truth).items()}
    slices = read_json(args.slices)
    scored = score_pair_table(pairs, model, calibrator)
    decisions = decide_queries(scored, truth, policy)
    predictions = {item.s1_entity_id: item.matched_entity_ids for item in decisions}
    report = evaluate_slices(truth, predictions, slices)
    all_metrics = report["all"]
    singleton_rate = all_metrics["singleton_false_positives"] / max(1, all_metrics["singletons"])
    metrics = {
        "model_macro_f05": all_metrics["macro_f05"],
        "singleton_false_positive_rate": singleton_rate,
        "runtime_seconds": time.perf_counter() - started,
        "peak_rss_mb": psutil.Process().memory_info().rss / 2**20,
    }
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "evaluation.json").write_text(json.dumps({"metrics": metrics, "slices": report}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    emit_metrics(metrics, stage="evaluation", experiment_id=args.experiment_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

