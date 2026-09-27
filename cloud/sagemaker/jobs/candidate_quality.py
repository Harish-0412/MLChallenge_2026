#!/usr/bin/env python3
"""Normalize Member B candidate metrics for the pipeline quality gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cloud.sagemaker.metrics import emit_metrics
from common import read_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="/opt/ml/processing/input/candidate-metrics")
    parser.add_argument("--output", default="/opt/ml/processing/output/quality")
    parser.add_argument("--experiment-id", required=True)
    args = parser.parse_args()
    source = read_json(args.input)
    report = {
        "candidate_recall": float(source["candidate_recall"]),
        "candidate_oracle_f05": float(source["candidate_oracle_f05"]),
    }
    if not all(0 <= value <= 1 for value in report.values()):
        raise ValueError("candidate quality metrics must be in [0, 1]")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "quality.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    emit_metrics(report, stage="candidate-quality", experiment_id=args.experiment_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

