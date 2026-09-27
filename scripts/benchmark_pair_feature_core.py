#!/usr/bin/env python3
"""Measure deterministic core pair-feature throughput/RSS at 10k and 100k rows."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modeling.pair_features import compute_pair_features  # noqa: E402


def entity(name: str, address: str) -> dict:
    return {
        "country": "OpenCountry", "name_key": name, "name_hyg": name, "name_core": name,
        "name_core_compact": name.replace(" ", ""), "name_latin_accent_key": name, "name_translit": name,
        "name_skeleton": name, "legal_form": "", "name_ninformative": 2, "name_scripts": 1,
        "name_placeholder_like": False, "name_is_domain_like": False, "name_has_control": False,
        "name_has_format": False, "name_mojibake": False, "address_missing": False,
        "address_canon": address, "address_tokset": address, "address_segments": [address],
        "address_state_canon": "state", "address_state_conf": "exact", "address_city_candidates": ["city"],
        "address_postal_candidates": ["12345"], "address_numbers_canon": ["12345"],
        "address_number_ctx": ["road 12345"], "address_parse_conf": "high", "address_has_control": False,
        "address_has_format": False, "address_mojibake": False,
    }


def run(count: int) -> dict:
    query, target = entity("acme services", "12 lake road 12345"), entity("acme service", "12 lake rd 12345")
    candidate = {"country": "OpenCountry", "retrieval_channels": ["name", "address"], "retrieval_scores": [.9, .8],
                 "retrieval_ranks": [1, 1], "candidate_block_size": 5, "query_candidate_count": 5}
    process = psutil.Process()
    before = process.memory_info().rss
    started = time.perf_counter()
    digest = 0.0
    for _ in range(count):
        digest += compute_pair_features(query, target, candidate)["name_core_ratio"]
    elapsed = time.perf_counter() - started
    return {"rows": count, "seconds": elapsed, "rows_per_second": count / elapsed, "rss_before": before,
            "rss_after": process.memory_info().rss, "digest": digest}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/modeling/pair_feature_core_benchmark.json")
    args = parser.parse_args()
    report = {"runs": [run(10_000), run(100_000)]}
    path = ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

