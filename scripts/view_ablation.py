#!/usr/bin/env python
"""Phase 8 – view ablation script.

This script analyses the built feature table for a given `FEATURE_VERSION`
(e.g. `feat_v2_0`).  For each generated view column it reports:
* total number of distinct values (`unique`)
* number of values that appear more than once (`collisions`)
* the collision rate as a percentage of distinct values.

The output is written as a CSV to `reports/eda/view_ablation_<version>.csv`
and also printed to stdout for quick inspection.

The implementation is deliberately lightweight – it only depends on the
standard library and `duckdb`.  The repository already declares `duckdb`
as a runtime dependency, so no extra installation steps are required.
"""

import argparse
import csv
import pathlib
import sys
from typing import List, Tuple

import duckdb

def analyse_views(feature_dir: pathlib.Path) -> List[Tuple[str, int, int, float]]:
    """Return statistics for each view column.

    Parameters
    ----------
    feature_dir: pathlib.Path
        Directory containing the parquet files for the feature version.

    Returns
    -------
    List of tuples `(column, unique, collisions, collision_rate)`.
    """
    # Load all parquet files in the directory.
    parquet_paths = list(feature_dir.glob("*.parquet"))
    if not parquet_paths:
        raise FileNotFoundError(f"No parquet files found in {feature_dir}")

    # Build a DuckDB connection and register the parquet files as a unified table.
    con = duckdb.connect()
    # Use a UNION ALL to combine all parts without materialising a huge table.
    sql_parts = [f"SELECT * FROM read_parquet('{p.as_posix()}')" for p in parquet_paths]
    union_sql = " UNION ALL ".join(sql_parts)
    con.sql(f"CREATE VIEW feature_data AS {union_sql}")

    # Determine the list of view columns – they are all columns except the raw input ones.
    # The raw columns are defined in `src/cleaning/record.py` as INPUT_COLUMNS.
    # We import that list dynamically to stay in sync.
    try:
        from src.cleaning.record import INPUT_COLUMNS
    except Exception:  # pragma: no cover – fallback if import fails.
        INPUT_COLUMNS = []
    all_cols = [row[0] for row in con.execute("PRAGMA table_info('feature_data')").fetchall()]
    view_cols = [c for c in all_cols if c not in INPUT_COLUMNS]

    results = []
    for col in view_cols:
        # Compute distinct count and collisions (>1 occurrences).
        distinct = con.execute(f"SELECT COUNT(DISTINCT {col}) FROM feature_data").fetchone()[0]
        collisions = con.execute(
            f"SELECT COUNT(*) FROM (SELECT {col} FROM feature_data GROUP BY {col} HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        rate = (collisions / distinct * 100.0) if distinct else 0.0
        results.append((col, distinct, collisions, rate))
    con.close()
    return results


def write_csv(results: List[Tuple[str, int, int, float]], out_path: pathlib.Path) -> None:
    """Write the ablation results to a CSV file.

    Columns: `view,unique,collisions,collision_rate_percent`.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["view", "unique", "collisions", "collision_rate_percent"])
        for col, unique, coll, rate in results:
            writer.writerow([col, unique, coll, f"{rate:.2f}"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", required=True, help="Feature version to analyse (e.g. feat_v2_0)")
    args = parser.parse_args()

    feature_dir = pathlib.Path("data/features") / args.version
    if not feature_dir.is_dir():
        sys.stderr.write(f"Feature directory not found: {feature_dir}\n")
        return 1

    try:
        results = analyse_views(feature_dir)
    except Exception as exc:  # pragma: no cover – unexpected runtime error.
        sys.stderr.write(str(exc) + "\n")
        return 1

    # Print a short human‑readable table.
    print("View ablation summary (version: {0})".format(args.version))
    print(f"{'view':30} {'unique':10} {'collisions':10} {'rate%':8}")
    for col, unique, coll, rate in results:
        print(f"{col:30} {unique:10} {coll:10} {rate:7.2f}%")

    csv_path = pathlib.Path("reports/eda") / f"view_ablation_{args.version}.csv"
    write_csv(results, csv_path)
    print(f"\nFull CSV written to {csv_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
