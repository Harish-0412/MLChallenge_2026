#!/usr/bin/env python3
"""SageMaker Training entry point for the calibrated GBDT and decision policy."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

import joblib
import numpy as np
import psutil

from cloud.sagemaker.metrics import emit_metrics
from modeling.calibration import fit_calibrator
from modeling.contracts import ScoredPair
from modeling.decision import search_policy
from modeling.models import GBDTConfig, train_gbdt
from modeling.pair_features import FEATURE_COLUMNS, feature_matrix
from common import read_json, read_parquet_tree, training_hyperparameters


def _channel(name: str) -> Path:
    return Path(os.environ.get(f"SM_CHANNEL_{name.upper().replace('-', '_')}", f"/opt/ml/input/data/{name}"))


def _truth(value) -> dict[str, tuple[str, ...]]:
    return {query_id: tuple(matches) for query_id, matches in value.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    # SageMaker's ModelTrainer launches custom images with the conventional
    # ``train`` command. Keep it optional so the same entry point remains
    # directly runnable for local smoke tests.
    parser.add_argument("command", nargs="?", choices=("train",))
    parser.add_argument("--backend", choices=("xgboost", "lightgbm"), default="xgboost")
    parser.add_argument("--seed", type=int, default=20260926)
    parser.add_argument("--n-estimators", type=int, default=500)
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--learning-rate", type=float, default=.05)
    parser.add_argument("--experiment-id", default=os.environ.get("EXPERIMENT_ID", "unknown"))
    args = parser.parse_args()
    hp = training_hyperparameters()
    args.backend = hp.get("backend", args.backend)
    args.seed = int(hp.get("seed", args.seed))
    args.n_estimators = int(hp.get("n_estimators", args.n_estimators))
    args.max_depth = int(hp.get("max_depth", args.max_depth))
    args.learning_rate = float(hp.get("learning_rate", args.learning_rate))
    args.experiment_id = hp.get("experiment_id", args.experiment_id)
    started = time.perf_counter()
    train = read_parquet_tree(_channel("train"))
    early = read_parquet_tree(_channel("early-stop"))
    calibration = read_parquet_tree(_channel("calibration"))
    truth = _truth(read_json(_channel("calibration-truth"), "*.json"))

    config = GBDTConfig(
        backend=args.backend, seed=args.seed, n_estimators=args.n_estimators,
        max_depth=args.max_depth, learning_rate=args.learning_rate,
        n_jobs=max(1, os.cpu_count() or 1),
    )
    model = train_gbdt(
        feature_matrix(train), train["is_positive"].to_numpy(),
        feature_matrix(early), early["is_positive"].to_numpy(),
        sample_weight=train["sample_weight"].to_numpy(), validation_weight=early["sample_weight"].to_numpy(),
        config=config,
    )
    raw_scores = model.predict_proba(feature_matrix(calibration))
    train_ids = set(train["s1_entity_id"].to_pylist()) | set(early["s1_entity_id"].to_pylist())
    calibration_ids = set(calibration["s1_entity_id"].to_pylist())
    calibrator = fit_calibrator(
        raw_scores, calibration["is_positive"].to_numpy(), method="isotonic",
        model_fit_query_ids=train_ids, calibration_query_ids=calibration_ids,
    )
    scores = calibrator.predict(raw_scores)
    scored = [
        ScoredPair(
            calibration["s1_entity_id"][i].as_py(), calibration["candidate_entity_id"][i].as_py(), float(score),
            calibration["country"][i].as_py(), calibration["evidence_slice"][i].as_py(),
        ) for i, score in enumerate(scores)
    ]
    policy, macro = search_policy(
        scored, truth,
        thresholds=(.5, .6, .7, .8, .85, .9, .93, .95, .97, .99),
        top_ks=(1, 2, 3, 5, 10), margins=(0, .02, .05, .1), max_cardinalities=(1, 2, 3, 5, 10),
    )
    model_dir = Path(os.environ.get("SM_MODEL_DIR", "/opt/ml/model"))
    output_dir = Path(os.environ.get("SM_OUTPUT_DATA_DIR", "/opt/ml/output/data"))
    model_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_dir / "model.joblib")
    joblib.dump(calibrator, model_dir / "calibrator.joblib")
    (model_dir / "policy.json").write_text(json.dumps({
        "threshold": policy.threshold, "top_k": policy.top_k, "min_top_margin": policy.min_top_margin,
        "max_cardinality": policy.max_cardinality, "slice_thresholds": list(policy.slice_thresholds),
        "version": policy.version,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (model_dir / "feature_names.json").write_text(json.dumps(list(FEATURE_COLUMNS)) + "\n", encoding="utf-8")
    elapsed = time.perf_counter() - started
    metrics = {"model_macro_f05": macro, "runtime_seconds": elapsed,
               "peak_rss_mb": psutil.Process().memory_info().rss / 2**20}
    (output_dir / "training_report.json").write_text(json.dumps({"metrics": metrics, "backend": args.backend}, indent=2) + "\n", encoding="utf-8")
    emit_metrics(metrics, stage="gbdt-training", experiment_id=args.experiment_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
