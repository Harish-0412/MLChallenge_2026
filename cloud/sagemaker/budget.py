"""Auditable local budget ledger; never calls AWS billing APIs."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
import json
from pathlib import Path
import tempfile
from typing import Iterable

from .foundation import BudgetPolicy, FoundationError, JobEstimate


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    job_name: str
    stage: str
    status: str
    estimated_usd: str
    actual_usd: str = "0"
    note: str = ""


def load_ledger(path: str | Path) -> dict:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"entries": []}


def committed_by_stage(ledger: dict) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    for entry in ledger.get("entries", []):
        if entry["status"] not in ("cancelled", "failed-before-start"):
            result[entry["stage"]] = result.get(entry["stage"], Decimal(0)) + Decimal(entry["estimated_usd"])
    return result


def reserve(path: str | Path, policy: BudgetPolicy, estimate: JobEstimate, note: str = "") -> LedgerEntry:
    path = Path(path)
    ledger = load_ledger(path)
    if any(entry["job_name"] == estimate.name for entry in ledger["entries"]):
        raise FoundationError(f"budget ledger already contains job {estimate.name}")
    policy.check_job(estimate, committed_by_stage(ledger))
    entry = LedgerEntry(estimate.name, estimate.stage, "planned", str(estimate.maximum_usd), note=note)
    ledger["entries"].append(asdict(entry))
    ledger["entries"].sort(key=lambda item: item["job_name"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as stream:
        json.dump(ledger, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)
    return entry

