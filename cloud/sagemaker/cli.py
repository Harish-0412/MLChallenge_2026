#!/usr/bin/env python3
"""Safe command line for validation, rendering, and explicit pipeline mutations."""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from .budget import committed_by_stage, load_ledger, reserve
from .foundation import (
    JobEstimate, assert_caller_matches_config, assert_safe_caller, budget_policy, load_foundation_config,
)
from .pipeline import build_pipeline


def _session(config, profile):
    return boto3.Session(profile_name=profile, region_name=config["region"])


def _identity(config, profile):
    return _session(config, profile).client("sts").get_caller_identity()


def _sample_estimates(config, mode, experiment_id):
    resource = config["resources"][mode]
    prices = config["resources"]["estimated_hourly_usd"]
    return [
        JobEstimate(f"{experiment_id}-processing-{index}", "infrastructure", resource["processing_instance"], 1,
                    resource["processing_max_seconds"], Decimal(str(prices[resource["processing_instance"]])))
        for index in range(1, 5)
    ] + [
        JobEstimate(f"{experiment_id}-gbdt", "gbdt", resource["training_instance"], 1,
                    resource["training_max_seconds"], Decimal(str(prices[resource["training_instance"]])))
    ]


def _create_or_update_pipeline(pipeline, config):
    client = pipeline.sagemaker_session.sagemaker_client
    try:
        client.describe_pipeline(PipelineName=pipeline.name)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in ("ResourceNotFound", "ValidationException"):
            raise
        return pipeline.create(
            role_arn=config["role_arn"], description="Entity resolution batch model pipeline", tags=config["tags"]
        )
    return pipeline.update(
        role_arn=config["role_arn"], description="Entity resolution batch model pipeline"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/sagemaker.json")
    parser.add_argument("--ledger", default="reports/modeling/aws_budget_ledger.json")
    parser.add_argument("--profile", required=True, help="Explicit non-root AWS CLI profile")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--mode", choices=("sample", "full"), default="sample")
    render = sub.add_parser("render")
    render.add_argument("--mode", choices=("sample", "full"), default="sample")
    render.add_argument("--output", required=True)
    upsert = sub.add_parser("upsert")
    upsert.add_argument("--mode", choices=("sample", "full"), default="sample")
    upsert.add_argument("--confirm", required=True)
    start = sub.add_parser("start")
    start.add_argument("--mode", choices=("sample", "full"), default="sample")
    start.add_argument("--parameters", required=True)
    start.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)
    config = load_foundation_config(args.config)

    if args.command == "validate":
        policy = budget_policy(config)
        committed = {}
        for estimate in _sample_estimates(config, args.mode, "validation"):
            policy.check_job(estimate, committed)
            committed[estimate.stage] = committed.get(estimate.stage, Decimal(0)) + estimate.maximum_usd
        identity = _identity(config, args.profile)
        safe = True
        try:
            assert_safe_caller(identity)
            assert_caller_matches_config(identity, config)
        except ValueError as exc:
            safe = False
            print(f"AWS_MUTATIONS_BLOCKED: {exc}")
        print(json.dumps({"config": "valid", "mode": args.mode, "caller_safe_for_mutation": safe,
                          "maximum_sample_plan_usd": str(sum(committed.values()))}, indent=2))
        return 0

    if args.command == "render":
        definition = json.loads(build_pipeline(config, mode=args.mode, offline=True,
                                                profile_name=args.profile).definition())
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(definition, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(destination)
        return 0

    identity = _identity(config, args.profile)
    assert_safe_caller(identity)
    assert_caller_matches_config(identity, config)
    expected = f"{args.command.upper()}-{args.mode.upper()}"
    if args.confirm != expected:
        raise ValueError(f"confirmation must be exactly {expected}")
    if args.command == "upsert":
        pipeline = build_pipeline(config, mode=args.mode, offline=False, profile_name=args.profile)
        response = _create_or_update_pipeline(pipeline, config)
        print(json.dumps(response, indent=2, default=str))
        return 0
    parameters = json.loads(Path(args.parameters).read_text(encoding="utf-8"))
    experiment = parameters.get("ExperimentId")
    if not experiment or not isinstance(experiment, str):
        raise ValueError("start parameters require a non-empty ExperimentId")
    policy = budget_policy(config)
    estimates = _sample_estimates(config, args.mode, experiment)
    committed = committed_by_stage(load_ledger(args.ledger))
    for estimate in estimates:
        policy.check_job(estimate, committed)
        committed[estimate.stage] = committed.get(estimate.stage, Decimal(0)) + estimate.maximum_usd
    for estimate in estimates:
        reserve(args.ledger, policy, estimate, note=f"reserved before {args.mode} pipeline start")
    pipeline = build_pipeline(config, mode=args.mode, offline=False, profile_name=args.profile)
    execution = pipeline.start(parameters=parameters, execution_display_name=parameters.get("ExperimentId"))
    print(json.dumps(execution.describe(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
