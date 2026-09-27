"""Consistent metric logging and optional CloudWatch custom metric emission."""
from __future__ import annotations

import json
import os
from typing import Mapping

METRIC_NAMES = (
    "candidate_recall", "candidate_oracle_f05", "model_macro_f05",
    "singleton_false_positive_rate", "runtime_seconds", "peak_rss_mb",
)


def emit_metrics(metrics: Mapping[str, float], *, stage: str, experiment_id: str) -> None:
    unknown = set(metrics) - set(METRIC_NAMES)
    if unknown:
        raise ValueError(f"unknown metrics: {sorted(unknown)}")
    for name in sorted(metrics):
        value = float(metrics[name])
        print(f"METRIC {name}={value:.10g}", flush=True)
        print(json.dumps({"event": "metric", "name": name, "value": value, "stage": stage,
                          "experiment_id": experiment_id}, sort_keys=True), flush=True)
    if os.environ.get("EMIT_CLOUDWATCH", "0") != "1" or not metrics:
        return
    import boto3

    namespace = os.environ.get("CLOUDWATCH_NAMESPACE", "MLChallenge/EntityResolution")
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    boto3.client("cloudwatch", region_name=region).put_metric_data(
        Namespace=namespace,
        MetricData=[{
            "MetricName": name,
            "Value": float(value),
            "Unit": "Seconds" if name == "runtime_seconds" else ("Megabytes" if name == "peak_rss_mb" else "None"),
            "Dimensions": [{"Name": "Stage", "Value": stage}, {"Name": "ExperimentId", "Value": experiment_id}],
        } for name, value in metrics.items()],
    )


TRAINING_METRIC_DEFINITIONS = [
    {"name": name.replace("_", ":", 1), "regex": rf"METRIC {name}=([0-9.eE+-]+)"}
    for name in METRIC_NAMES
]
