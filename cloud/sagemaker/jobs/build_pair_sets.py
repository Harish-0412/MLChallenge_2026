#!/usr/bin/env python3
"""Build train/early-stop/calibration/holdout/test pair partitions in one Processing job."""
from __future__ import annotations

import argparse
from pathlib import Path
import time

import psutil

from cloud.sagemaker.metrics import emit_metrics
from modeling.pair_features import build_pair_table
from common import find_one

PARTITIONS = ("train", "early-stop", "calibration", "holdout", "test")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", default="/opt/ml/processing/input/features")
    parser.add_argument("--candidates", default="/opt/ml/processing/input/candidates")
    parser.add_argument("--output", default="/opt/ml/processing/output/pairs")
    parser.add_argument("--mode", choices=("sample", "full"), default="sample")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=50_000)
    args = parser.parse_args()
    started = time.perf_counter()
    total = 0
    for partition in PARTITIONS:
        source = Path(args.candidates) / partition
        destination = Path(args.output) / partition
        destination.mkdir(parents=True, exist_ok=True)
        report = build_pair_table(
            args.features, find_one(source, "*.parquet"), destination / "pairs.parquet",
            batch_size=args.batch_size, threads=args.threads,
        )
        total += report["pair_rows"]
    emit_metrics({"runtime_seconds": time.perf_counter() - started,
                  "peak_rss_mb": psutil.Process().memory_info().rss / 2**20},
                 stage="pair-build", experiment_id=args.experiment_id)
    print(f"PAIR_ROWS_TOTAL={total}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
