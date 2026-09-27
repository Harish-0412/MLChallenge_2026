"""Deterministic configuration, hashing, logging, and experiment manifests."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import random
import subprocess
from typing import Any, Mapping

from .contracts import ExperimentReport


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def load_json_config(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("configuration root must be an object")
    return value


def config_hash(config: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(config).encode("utf-8")).hexdigest()


def sha256_file(path: str | Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def source_revision(root: str | Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(root), text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def set_global_seed(seed: int) -> None:
    if seed < 0:
        raise ValueError("seed must be non-negative")
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for name in ("experiment_id", "stage", "metric", "value"):
            if hasattr(record, name):
                payload[name] = getattr(record, name)
        return canonical_json(payload)


def write_experiment_report(report: ExperimentReport, path: str | Path) -> None:
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite experiment report: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report.to_mapping(), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

