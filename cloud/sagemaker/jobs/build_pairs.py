#!/usr/bin/env python3
"""SageMaker Processing entry point: feature records + candidates -> pair features."""
from __future__ import annotations

import argparse
from pathlib import Path
import time

import psutil

from modeling.pair_features import build_pair_table
from cloud.sagemaker.metrics import emit_metrics
from common import find_one


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
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    manifest = build_pair_table(
        args.features, find_one(args.candidates, "*.parquet"), output / "pairs.parquet",
        batch_size=args.batch_size, threads=args.threads,
    )
    elapsed = time.perf_counter() - started
    emit_metrics({"runtime_seconds": elapsed, "peak_rss_mb": psutil.Process().memory_info().rss / 2**20},
                 stage="pair-build", experiment_id=args.experiment_id)
    print(f"PAIR_ROWS={manifest['pair_rows']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

