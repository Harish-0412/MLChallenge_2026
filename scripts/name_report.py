"""Phase 3 verification over ALL rows of the six Parquet copies, plus the Source 1 collision table.

    python scripts/name_report.py                 # full scan; writes reports/cleaning/name_*
    python scripts/name_report.py --max-groups 3  # smoke run; writes nothing

Outputs (reports/cleaning/): name_scan_counts.csv, name_verification.json, name_view_collisions.csv, name_examples.md.
Independent checks: four counts are recomputed with DuckDB SQL (a different engine and regex dialect) and must equal the
Python counts; placeholder counts must also equal the audit's own SQL numbers. Exit code 0 only if every check passes.
"""
import argparse
import csv
import json
import shutil
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import duckdb  # noqa: E402

from cleaning import name_scan as scan  # noqa: E402
from cleaning.lexicons import all_lexicon_hashes  # noqa: E402
from cleaning.manifest import SOURCE_TABLES  # noqa: E402

OUT = ROOT / 'reports' / 'cleaning'
INTERIM = ROOT / 'data' / 'interim'
SCRATCH = ROOT / 'data' / 'scratch' / 'phase3_s1_keys'
VIEWS = ['name_key', 'name_hyg', 'name_latin_accent_key', 'name_core', 'name_core_fold', 'name_core_trim', 'name_core_set', 'name_core_compact', 'name_skeleton']
SCRIPT_KEYS = ['Devanagari', 'Bengali', 'Gurmukhi', 'Gujarati', 'Oriya', 'Tamil', 'Telugu', 'Kannada', 'Malayalam']


def tasks(max_groups):
    import pyarrow.parquet as pq
    out = []
    for table in SOURCE_TABLES:
        path = INTERIM / f'{table}.parquet'
        groups = pq.ParquetFile(path).num_row_groups
        scratch = str(SCRATCH) if table.endswith('source1') else None
        out += [(table, str(path), g, scratch) for g in range(groups if not max_groups else min(groups, max_groups))]
    return out


def sql_counts(con):
    """Independent recomputation in DuckDB (RE2 regex dialect) of four quantities, per table and country."""
    result = {}
    for table in SOURCE_TABLES:
        path = (INTERIM / f'{table}.parquet').as_posix()
        for country, placeholder, domain, prefix, ms in con.execute(f"""SELECT country,
            count_if(lower(trim(business_name)) IN ('na','n/a','null','none','nan','unknown','-')),
            count_if(regexp_full_match(trim(business_name), '(?i)[A-Za-z0-9-]+(\\.[A-Za-z0-9-]+)*\\.com')),
            count_if(regexp_matches(trim(business_name), '^[*>.#@_~|=+!-]')),
            count_if(regexp_matches(business_name, '^\\s*[Mm]\\s*/\\s*[Ss]([^A-Za-z]|$)'))
            FROM read_parquet('{path}') GROUP BY country""").fetchall():
            result[(table, country)] = {'placeholder': placeholder, 'domain_like': domain, 'noise_prefix': prefix, 'ms_pattern_rows': ms}
    return result


def script_census_check(counts):
    """Exact comparison of the Python script bitmask with the EDA's independent DuckDB script census (text_quality_details.json)."""
    census = json.loads((ROOT / 'reports' / 'eda' / 'text_quality_details.json').read_text(encoding='utf-8'))['script_census']
    mismatches, compared = [], 0
    for table, rows in census.items():
        for row in rows:
            for script in SCRIPT_KEYS:
                for field in ('name', 'address'):
                    theirs = row[f'{script.lower()}_{field}']
                    mine = counts.get((table, row['country'], f'script:{script}:{field}'), 0)
                    compared += 1
                    if mine != theirs:
                        mismatches.append({'table': table, 'country': row['country'], 'script': script, 'field': field, 'python': mine, 'eda_sql': theirs})
    other_expected = sum(row[f'{s}_{f}'] for rows in census.values() for row in rows for s in ('arabic', 'cyrillic', 'han') for f in ('name', 'address'))
    other_mine = sum(v for (_t, _c, k), v in counts.items() if k == 'other_script_rows')
    return mismatches, compared, other_mine, other_expected


def collisions(con):
    rows = []
    for table in ('train_source1', 'test_source1'):
        for view in VIEWS:
            for country, n, distinct, shared_rows, largest in con.execute(f"""
                SELECT country, sum(g), count(*), sum(CASE WHEN g>1 THEN g ELSE 0 END), max(g)
                FROM (SELECT country, {view} AS k, count(*) AS g FROM read_parquet('{(SCRATCH / (table + '_*.parquet')).as_posix()}')
                      WHERE {view} <> '' GROUP BY country, {view}) GROUP BY country ORDER BY country""").fetchall():
                rows.append({'table': table, 'country': country, 'view': view, 'rows': n, 'distinct_keys': distinct,
                             'rows_sharing_a_key': shared_rows, 'percent_rows_sharing': round(100 * shared_rows / n, 2),
                             'largest_group': largest})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--workers', type=int, default=5)
    parser.add_argument('--max-groups', type=int, default=0)
    args = parser.parse_args()
    full = not args.max_groups
    audit = json.loads((ROOT / 'reports' / 'eda' / 'full_audit.json').read_text(encoding='utf-8'))
    manifest = json.loads((ROOT / 'manifests' / 'input_manifest_v1.json').read_text(encoding='utf-8'))
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    work = tasks(args.max_groups)
    print(f'{len(work)} row-group tasks, {args.workers} workers', flush=True)
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = []
        for i, result in enumerate(pool.map(scan.scan_row_group, work, chunksize=1), 1):
            results.append(result)
            if i % 40 == 0 or i == len(work):
                print(f'  {i}/{len(work)} row groups, {sum(r["rows"] for r in results):,} rows, {time.perf_counter() - started:.0f}s', flush=True)
    merged = scan.merge(results)
    wall = time.perf_counter() - started
    counts = merged['counts']
    total = lambda m: sum(v for (t, c, k), v in counts.items() if k == m)
    violations = {k: total(k) for k in sorted({k for (_t, _c, k) in counts if k.startswith('violation:')})}

    checks = {'no_structural_violations': all(v == 0 for v in violations.values())}
    con = duckdb.connect()
    con.execute("SET memory_limit='4GB'")
    con.execute('SET threads=4')
    sql = sql_counts(con)
    mismatches = []
    for (table, country), expected in sql.items():
        for metric, value in expected.items():
            mine = counts.get((table, country, metric), 0)
            if args.max_groups:
                continue
            if mine != value:
                mismatches.append({'table': table, 'country': country, 'metric': metric, 'python': mine, 'sql': value})
    audit_mismatches = []
    for table in SOURCE_TABLES:
        for p in audit['profiles'][table]:
            mine = counts.get((table, p['country'], 'placeholder'), 0)
            if full and mine != p['name_placeholder_like']:
                audit_mismatches.append({'table': table, 'country': p['country'], 'python': mine, 'audit_sql': p['name_placeholder_like']})
    if full:
        checks['every_row_scanned'] = merged['rows'] == manifest['totals']['source_rows']
        checks['python_counts_equal_independent_sql'] = not mismatches
        checks['placeholder_counts_equal_audit_sql'] = not audit_mismatches
        script_mismatches, script_compared, other_mine, other_expected = script_census_check(counts)
        checks['script_bitmask_equals_eda_census_exactly'] = not script_mismatches
        checks['no_other_scripts_as_in_eda'] = other_mine == other_expected == 0
        collision_rows = collisions(con)
    verification = {
        'rows_scanned': merged['rows'], 'wall_seconds': round(wall, 1), 'rows_per_second_wall': round(merged['rows'] / wall),
        'us_per_row_cpu': round(1e6 * merged['seconds'] / max(merged['rows'], 1), 1), 'peak_worker_memory_mb': merged['peak_memory_mb'],
        'violations': violations, 'sql_mismatches': mismatches, 'audit_mismatches': audit_mismatches,
        'script_census': {'cells_compared': script_compared if full else 0, 'mismatches': script_mismatches if full else [], 'other_script_rows': other_mine if full else None},
        'lexicon_sha256': all_lexicon_hashes(), 'checks': checks, 'passed': all(checks.values()),
        'totals': {m: total(m) for m in ['rows', 'has_legal_form', 'fallback', 'placeholder', 'domain_like', 'noise_prefix', 'bracket_text',
                                         'ms_pattern_rows', 'ninformative_0', 'ninformative_1', 'core_differs_v1', 'trim_changes',
                                         'indic_names', 'mixed_script_names', 'indic_names_with_legal_form']},
    }
    print(json.dumps({k: verification[k] for k in ['rows_scanned', 'wall_seconds', 'us_per_row_cpu', 'peak_worker_memory_mb', 'violations', 'checks', 'passed']}, indent=2))
    if mismatches or audit_mismatches:
        print('MISMATCHES', mismatches[:6], audit_mismatches[:6])
    if not full:
        print('smoke run: nothing written')
        return 0 if verification['passed'] else 1

    OUT.mkdir(parents=True, exist_ok=True)
    row_counts = {(t, c): v for (t, c, k), v in counts.items() if k == 'rows'}
    with (OUT / 'name_scan_counts.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['table', 'country', 'metric', 'count', 'rows', 'percent'])
        for (t, c, k), v in sorted(counts.items()):
            writer.writerow([t, c, k, v, row_counts[(t, c)], f'{100 * v / row_counts[(t, c)]:.4f}'])
    with (OUT / 'name_view_collisions.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(collision_rows[0]))
        writer.writeheader()
        writer.writerows(collision_rows)
    verification['collisions_file'] = 'name_view_collisions.csv'
    (OUT / 'name_verification.json').write_text(json.dumps(verification, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    with (OUT / 'name_examples.md').open('w', encoding='utf-8', newline='\n') as stream:
        stream.write('# Name feature examples\n\nFirst four rows (by entity ID) per category over all six files: raw name, then the value.\n')
        for kind, items in sorted(merged['examples'].items()):
            stream.write(f'\n## {kind}\n\n')
            for eid, raw, value in items:
                stream.write(f'- {eid}: `{raw!r}` -> `{value}`\n')
    print('wrote name_scan_counts.csv, name_view_collisions.csv, name_verification.json, name_examples.md')
    return 0 if verification['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
