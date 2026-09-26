"""Member B / B5 (France): candidate statistics for the UNLABELED French test queries. No accuracy is claimed: only counts, zero-candidate rate,
script/accent/missing-address coverage and a few examples, computed with the same channels against the French test targets.

    python scripts/france_candidate_report.py [--queries 5000]

Output: reports/eda/france_candidate_report.md / .json.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from retrieval import engine  # noqa: E402

FEATURES = ROOT / 'data' / 'features' / 'feat_v2_0' / 'split=test'
OUT = ROOT / 'reports' / 'eda'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--queries', type=int, default=5000)
    args = parser.parse_args()
    started = time.perf_counter()
    con = duckdb.connect()
    con.execute("SET threads=8; SET memory_limit='10GB'")
    cols = ', '.join(engine.FEATURE_COLUMNS)
    derived = ', '.join(f'{expr} AS {name}' for name, expr in engine.DERIVED.items())
    q_glob = (FEATURES / 'source=1' / 'country=France' / '*.parquet').as_posix()
    t_glob = (FEATURES / 'source=[23]' / 'country=France' / '*.parquet').as_posix()
    con.execute(f"""CREATE TEMP TABLE bq AS
        SELECT row_number() OVER (ORDER BY entity_id)::INT AS qid, {cols}, {derived}, name_scripts, name_latin_accent_key FROM (
            SELECT {cols}, name_scripts, name_latin_accent_key FROM read_parquet('{q_glob}', hive_partitioning=false)
            ORDER BY sha256('france-report|' || entity_id) LIMIT {args.queries})""")
    con.execute(f"""CREATE TEMP TABLE tt AS
        SELECT row_number() OVER (ORDER BY entity_id)::INT AS tid, {cols}, {derived}, name_scripts, name_latin_accent_key
        FROM (SELECT {cols}, name_scripts, name_latin_accent_key FROM read_parquet('{t_glob}', hive_partitioning=false))""")
    con.execute('CREATE OR REPLACE TEMP TABLE cand (channel VARCHAR, qid INT, tid INT, rnk INT, score DOUBLE, blk INT)')
    con.execute('CREATE OR REPLACE TEMP TABLE chan_stats (channel VARCHAR, seconds DOUBLE, pairs_before_cap BIGINT, oversize_blocks BIGINT, note VARCHAR)')
    n_q, n_t = con.execute('SELECT (SELECT count(*) FROM bq), (SELECT count(*) FROM tt)').fetchone()
    print(f'France test: {n_q:,} sampled queries (of 259,452) vs {n_t:,} targets; running channels', flush=True)
    engine.run_all_channels(con, log=lambda m: print(m, flush=True))

    def stats(where):
        return con.execute(f"""
            WITH per AS (SELECT q.qid, count(DISTINCT c.tid) AS n FROM bq q LEFT JOIN cand c ON c.qid = q.qid AND ({where}) GROUP BY q.qid)
            SELECT avg(n), quantile_cont(n, 0.5), quantile_cont(n, 0.9), quantile_cont(n, 0.99), max(n), avg((n = 0)::INT) FROM per""").fetchone()
    channels = [c['name'] for c in engine.EQUALITY_CHANNELS + engine.POSTINGS_CHANNELS]
    result = {'queries': n_q, 'targets': n_t, 'channels': {}, 'unions': {}}
    for ch in channels:
        r = stats(f"channel = '{ch}'")
        result['channels'][ch] = dict(zip(['mean', 'p50', 'p90', 'p99', 'max', 'zero_rate'], map(float, r)))
    for label, cond in (('v1 exact keys', "channel IN ('eq_name_key', 'eq_address_key')"),
                        ('union sparse k=20', ' OR '.join([f"(channel = '{c}' AND rnk <= {engine.MAX_K})" for c in channels if c.startswith('eq_')]
                                                          + [f"(channel = '{c}' AND rnk <= 20)" for c in channels if not c.startswith('eq_')])),
                        ('union sparse k=100', 'true')):
        result['unions'][label] = dict(zip(['mean', 'p50', 'p90', 'p99', 'max', 'zero_rate'], map(float, stats(cond))))
    cov = con.execute("""SELECT avg((name_key <> name_latin_accent_key)::INT), avg(address_missing::INT), avg(((name_scripts & 1022) > 0)::INT) FROM bq""").fetchone()
    tcov = con.execute("""SELECT avg((name_key <> name_latin_accent_key)::INT), avg(address_missing::INT), avg(((name_scripts & 1022) > 0)::INT) FROM tt""").fetchone()
    result['coverage'] = {'queries': {'accented_name': cov[0], 'address_missing': cov[1], 'indic_script_name': cov[2]},
                          'targets': {'accented_name': tcov[0], 'address_missing': tcov[1], 'indic_script_name': tcov[2]}}
    result['examples'] = [dict(zip(['query_name', 'query_address', 'top_candidate_name', 'top_candidate_address', 'channel'], r)) for r in con.execute("""
        SELECT q.business_name_placeholder, q.address_canon, t.name_core, t.address_canon, c.channel FROM (
            SELECT qid, name_core AS business_name_placeholder, address_canon FROM bq ORDER BY qid LIMIT 8) q
        JOIN cand c ON c.qid = q.qid AND c.rnk = 1 AND c.channel = 'bigram_address' JOIN tt t ON t.tid = c.tid""").fetchall()]
    result['seconds'] = time.perf_counter() - started
    (OUT / 'france_candidate_report.json').write_text(json.dumps(result, indent=2, default=float) + '\n', encoding='utf-8', newline='\n')
    md = ['# France candidate report (unlabeled; counts only, no accuracy claim)', '',
          f'{n_q:,} deterministic French test queries (of 259,452) against the {n_t:,} French test targets (S2 703,378 + S3 731,615), same channels and parameters as for India/US '
          '(the document-frequency caps were set on India/US corpora and not retuned for France). Candidates are features-only; there is no way to measure recall.', '',
          '## Candidates per query', '', '| set | mean | p50 | p90 | p99 | max | queries with none |', '|---|---:|---:|---:|---:|---:|---:|']
    for label, s in list(result['unions'].items()) + list(result['channels'].items()):
        md.append(f"| {label} | {s['mean']:.1f} | {s['p50']:.0f} | {s['p90']:.0f} | {s['p99']:.0f} | {s['max']:.0f} | {100 * s['zero_rate']:.2f}% |")
    md += ['', '## Text coverage (share of records)', '', '| | accented name | address missing | Indic-script name |', '|---|---:|---:|---:|']
    for k, v in result['coverage'].items():
        md.append(f"| {k} | {100 * v['accented_name']:.1f}% | {100 * v['address_missing']:.1f}% | {100 * v['indic_script_name']:.2f}% |")
    md += ['', 'A high zero-candidate rate for the exact-key channels is expected (labels show that only about 29% of true links share an exact key in India/US). '
           'What matters is that the union has few empty queries and a candidate count in the same range as India/US (mean 86 / p99 223 at k = 20); a large deviation would signal that a channel threshold does not transfer to France.']
    (OUT / 'france_candidate_report.md').write_text('\n'.join(md) + '\n', encoding='utf-8', newline='\n')
    print('\n'.join(md[:16]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
