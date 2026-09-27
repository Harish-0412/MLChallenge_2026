"""Versioned S3 paths, immutable settings, identity checks, and budget guards."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
import re
from typing import Any, Mapping

_SAFE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


class FoundationError(ValueError):
    pass


def _segment(value: str, label: str) -> str:
    if not _SAFE.fullmatch(value):
        raise FoundationError(f"unsafe {label}: {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class S3Layout:
    bucket: str
    project: str = "entity-resolution"

    def __post_init__(self) -> None:
        _segment(self.bucket, "bucket")
        _segment(self.project, "project")

    @property
    def root(self) -> str:
        return f"s3://{self.bucket}/{self.project}"

    def versioned(self, kind: str, version: str) -> str:
        return f"{self.root}/{_segment(kind, 'artifact kind')}/{_segment(version, 'artifact version')}"

    def paths(self, versions: Mapping[str, str]) -> dict[str, str]:
        expected = {"features", "folds", "candidates", "pairs", "experiments", "models", "predictions", "submissions"}
        if set(versions) != expected:
            raise FoundationError(f"version map mismatch; expected={sorted(expected)}, actual={sorted(versions)}")
        return {kind: self.versioned(kind, versions[kind]) for kind in sorted(expected)}

    def execution(self, pipeline_name: str, execution_id: str) -> str:
        return f"{self.root}/pipeline-executions/{_segment(pipeline_name, 'pipeline name')}/{_segment(execution_id, 'execution ID')}"

    def code(self, source_hash: str) -> str:
        return self.versioned("code", source_hash)

    def checkpoints(self, job_name: str) -> str:
        return self.versioned("checkpoints", job_name)


@dataclass(frozen=True, slots=True)
class JobEstimate:
    name: str
    stage: str
    instance_type: str
    instance_count: int
    max_runtime_seconds: int
    estimated_hourly_usd: Decimal

    @property
    def maximum_usd(self) -> Decimal:
        hours = Decimal(self.max_runtime_seconds) / Decimal(3600)
        return (hours * Decimal(self.instance_count) * self.estimated_hourly_usd).quantize(Decimal("0.01"))


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    total_usd: Decimal
    contingency_usd: Decimal
    stage_limits: Mapping[str, Decimal]
    max_single_job_usd: Decimal
    max_tuning_job_usd: Decimal

    @property
    def spendable_usd(self) -> Decimal:
        return self.total_usd - self.contingency_usd

    def check_job(self, estimate: JobEstimate, committed_by_stage: Mapping[str, Decimal] | None = None) -> None:
        committed = committed_by_stage or {}
        cost = estimate.maximum_usd
        if cost > self.max_single_job_usd:
            raise FoundationError(f"{estimate.name} maximum ${cost} exceeds single-job cap ${self.max_single_job_usd}")
        if estimate.stage not in self.stage_limits:
            raise FoundationError(f"unbudgeted stage: {estimate.stage}")
        projected = Decimal(committed.get(estimate.stage, 0)) + cost
        if projected > self.stage_limits[estimate.stage]:
            raise FoundationError(
                f"{estimate.stage} projected ${projected} exceeds stage allocation ${self.stage_limits[estimate.stage]}"
            )
        if sum((Decimal(value) for value in committed.values()), Decimal(0)) + cost > self.spendable_usd:
            raise FoundationError("projected spend would consume the contingency reserve")


def load_foundation_config(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {"region", "bucket", "project", "role_arn", "images", "kms_key_arn", "tags", "resources", "budget"}
    missing = required - set(config)
    if missing:
        raise FoundationError(f"missing configuration keys: {sorted(missing)}")
    if any(value.startswith("REPLACE_") for value in (config["bucket"], config["role_arn"], *config["images"].values())):
        raise FoundationError("configuration still contains REPLACE_ placeholders")
    if config["region"] != "us-east-1":
        raise FoundationError("region differs from the project-approved us-east-1 region")
    if not config["role_arn"].startswith("arn:aws:iam::") or ":role/" not in config["role_arn"]:
        raise FoundationError("role_arn must be a SageMaker execution-role ARN")
    S3Layout(config["bucket"], config["project"])
    return config


def budget_policy(config: Mapping[str, Any]) -> BudgetPolicy:
    raw = config["budget"]
    return BudgetPolicy(
        Decimal(str(raw["total_usd"])), Decimal(str(raw["contingency_usd"])),
        {name: Decimal(str(value)) for name, value in raw["stage_limits_usd"].items()},
        Decimal(str(raw["max_single_job_usd"])), Decimal(str(raw["max_tuning_job_usd"])),
    )


def assert_safe_caller(identity: Mapping[str, str]) -> None:
    arn = identity.get("Arn", "")
    if arn.endswith(":root"):
        raise FoundationError(
            "refusing an AWS mutation with root credentials; use IAM Identity Center or an assumed deployment role"
        )
    if not (":assumed-role/" in arn or ":user/" in arn):
        raise FoundationError(f"unsupported AWS caller identity: {arn!r}")


def assert_caller_matches_config(identity: Mapping[str, str], config: Mapping[str, Any]) -> None:
    account = identity.get("Account", "")
    role_match = re.match(r"^arn:aws:iam::(\d{12}):role/", str(config["role_arn"]))
    if not role_match:
        raise FoundationError("unable to determine account from role_arn")
    expected = role_match.group(1)
    if account != expected:
        raise FoundationError(f"AWS caller account {account!r} differs from configured account {expected!r}")
    expected_registry = f"{expected}.dkr.ecr.{config['region']}.amazonaws.com/"
    if any(not str(uri).startswith(expected_registry) for uri in config["images"].values()):
        raise FoundationError("configured ECR images must use the configured account and region")
