"""Member B / B2: build and check the frozen validation folds (protocol val_v1).

    python scripts/build_fold_manifest.py            # build data/splits/fold_manifest_v1.parquet (+ stress) and run every leakage check
    python scripts/build_fold_manifest.py --check    # rebuild into a scratch file and require identical membership (content digest)

Inputs: data/interim/audit.duckdb (training tables and ground truth; read-only). Outputs (see reports/eda/validation_protocol.md):
    data/splits/fold_manifest_v1.parquet          main protocol (entity split)
    data/splits/fold_manifest_stress_v1.parquet   stress protocol (same-name S1 groups never split)
    reports/eda/fold_manifest_v1.json             counts, content digest, balance audit
    reports/eda/fold_leakage_report.json / .md    result of every check in src/validation/leakage.py
"""
import argparse
import json
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from validation import PROTOCOL_VERSION, leakage, splits  # noqa: E402

AUDIT = ROOT / 'data' / 'interim' / 'audit.duckdb'
OUT_DIR = ROOT / 'data' / 'splits'
REPORT_DIR = ROOT / 'reports' / 'eda'


def connect():
    con = duckdb.connect()
    con.execute("SET threads=8; SET memory_limit='10GB'")
    con.execute(f"ATTACH '{AUDIT.as_posix()}' AS a (READ_ONLY)")
    con.execute("CREATE VIEW s1 AS SELECT entity_id, country FROM a.train_source1")
    con.execute("CREATE VIEW s1_keys AS SELECT entity_id, country, name_key FROM a.train_source1")
    con.execute("""CREATE VIEW targets AS
        SELECT entity_id, 2 AS source, country FROM a.train_source2 UNION ALL SELECT entity_id, 3, country FROM a.train_source3""")
    con.execute("CREATE VIEW truth_pairs AS SELECT source1_entity_id, target_id FROM a.truth_pairs")
    return con


def digest(con, path: str) -> str:
    return con.execute(f"""SELECT sha256(string_agg(role || '|' || entity_id || '|' || fold, ',' ORDER BY role, entity_id))
                           FROM read_parquet('{path}')""").fetchone()[0]


def balance(con, path: str) -> dict:
    rows = con.execute(f"""
        SELECT q.fold, q.country, count(*) AS queries, count(*) FILTER (WHERE q.match_count = 0) AS singletons,
               count(*) FILTER (WHERE q.match_count >= 1) AS matched, sum(q.match_count) AS links
        FROM read_parquet('{path}') q WHERE q.role = 'query' GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()
    per_fold = {}
    for fold, country, n, single, matched, links in rows:
        per_fold.setdefault(fold, {})[country] = {'queries': n, 'singletons': single, 'singleton_fraction': single / n, 'links': int(links or 0),
                                                   'links_per_query': (links or 0) / n}
    targets = con.execute(f"""SELECT fold, assignment, source, count(*) FROM read_parquet('{path}') WHERE role = 'target' GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""").fetchall()
    return {'queries': per_fold, 'targets': [{'fold': f, 'assignment': a, 'source': int(s), 'count': n} for f, a, s, n in targets]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='rebuild into a scratch file and compare the content digest with the frozen manifest')
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    main_path, stress_path = OUT_DIR / 'fold_manifest_v1.parquet', OUT_DIR / 'fold_manifest_stress_v1.parquet'
    con = connect()
    started = time.perf_counter()
    if args.check:
        scratch = OUT_DIR / '_check_manifest.parquet'
        splits.build_manifest(con, scratch.as_posix())
        same = digest(con, scratch.as_posix()) == digest(con, main_path.as_posix())
        scratch.unlink()
        print('membership identical to the frozen manifest:', same)
        return 0 if same else 1
    if main_path.exists() or stress_path.exists():
        print(f'refusing: {main_path.name} is frozen; delete it deliberately (and bump the protocol version) to rebuild', file=sys.stderr)
        return 2
    counts = splits.build_manifest(con, main_path.as_posix())
    stress_counts = splits.build_stress_manifest(con, stress_path.as_posix())
    print('built', main_path.name, counts, '|', stress_path.name, stress_counts, f'({time.perf_counter() - started:.0f}s)', flush=True)
    checks = leakage.run_checks(con, main_path.as_posix(), stress_manifest=stress_path.as_posix())
    for name, ok, detail in checks:
        print(('PASS  ' if ok else 'FAIL  ') + name + (f'   [{detail}]' if detail else ''))
    groups = con.execute(f"""SELECT country, count(DISTINCT group_id), max(group_size), quantile_cont(group_size, 0.99), count(*) FILTER (WHERE group_size > 1)
                             FROM read_parquet('{stress_path.as_posix()}') WHERE role = 'query' GROUP BY 1 ORDER BY 1""").fetchall()
    summary = {
        'protocol': PROTOCOL_VERSION, 'seed': splits.SEED, 'fractions': '80/10/10', 'buckets': list(splits.BUCKETS),
        'main_manifest': {'file': main_path.name, 'rows': sum(counts.values()), 'rows_by_fold': counts, 'content_digest': digest(con, main_path.as_posix()),
                          'file_sha256_note': 'parquet bytes may differ across DuckDB versions; the content digest is the contract'},
        'stress_manifest': {'file': stress_path.name, 'rows_by_fold': stress_counts, 'content_digest': digest(con, stress_path.as_posix()),
                            'groups_by_country': [{'country': c, 'groups': g, 'largest': int(mx), 'p99_size': float(p99), 'queries_in_shared_name_groups': n}
                                                  for c, g, mx, p99, n in groups]},
        'balance': balance(con, main_path.as_posix()),
        'checks_passed': sum(ok for _n, ok, _d in checks), 'checks_total': len(checks),
    }
    (REPORT_DIR / 'fold_manifest_v1.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8', newline='\n')
    lines = ['# Fold leakage and integrity report (val_v1)', '', f'{summary["checks_passed"]}/{summary["checks_total"]} checks pass.', '']
    lines += [f'- {"PASS" if ok else "**FAIL**"} {name}' + (f' - {detail}' if detail else '') for name, ok, detail in checks]
    (REPORT_DIR / 'fold_leakage_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    (REPORT_DIR / 'fold_leakage_report.json').write_text(json.dumps([{'name': n, 'ok': o, 'detail': d} for n, o, d in checks], indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'{summary["checks_passed"]}/{summary["checks_total"]} checks passed')
    return 0 if summary['checks_passed'] == summary['checks_total'] else 1


if __name__ == '__main__':
    sys.exit(main())
