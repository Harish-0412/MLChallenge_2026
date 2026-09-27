"""Shared SageMaker job I/O helpers."""
from __future__ import annotations

import json
from pathlib import Path
import tarfile

import pyarrow as pa
import pyarrow.parquet as pq


def find_one(root: str | Path, pattern: str) -> Path:
    matches = sorted(Path(root).rglob(pattern))
    if len(matches) != 1:
        raise ValueError(f"expected one {pattern} below {root}, found {len(matches)}")
    return matches[0]


def read_parquet_tree(root: str | Path) -> pa.Table:
    files = sorted(Path(root).rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no Parquet files below {root}")
    return pa.concat_tables([pq.read_table(path) for path in files], promote_options="default")


def read_json(root: str | Path, pattern: str = "*.json"):
    return json.loads(find_one(root, pattern).read_text(encoding="utf-8"))


def training_hyperparameters() -> dict[str, str]:
    path = Path("/opt/ml/input/config/hyperparameters.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def safe_extract_model(model_input: str | Path, destination: str | Path) -> Path:
    archive = find_one(model_input, "*.tar.gz")
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        for member in members:
            target = (destination / member.name).resolve()
            if destination not in target.parents and target != destination:
                raise ValueError(f"unsafe model archive member: {member.name}")
        bundle.extractall(destination, members=members, filter="data")
    return destination
