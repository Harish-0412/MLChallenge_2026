"""Build blocking candidates for the REAL competition test set (all countries found in test_source1, open-set: US, India, France and any other label).

    python scripts/test_candidates.py [--threads 8] [--memory 10GB] [--sparse-k 20] [--limit-per-country 0] [--countries India,US,France]

Every test Source-1 query and the complete test Source-2/3 corpus of its country are used (there is no train/dev/val/holdout fold here: the test set has
no labels and is scored elsewhere). Candidate generation touches ONLY the feature columns; no label exists to touch.

Sparse channels (token/trigram/bigram postings) are capped at ``--sparse-k`` per channel when written (default 20, per the "smaller candidate set scores
higher" rule); equality channels keep every match they find (already self-limiting: oversize blocks are ranked and capped inside src/retrieval/engine.py).

Output: data/test_output/candidates_<country>.parquet (channel, q, t, rnk, score, blk) and data/test_output/test_candidates_manifest.json.
On a big machine, raise --threads and --memory; DuckDB parallelises each channel internally, so no process-level sharding is needed here.
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
OUT = ROOT / 'data' / 'test_output'
SPARSE_NAMES = [c['name'] for c in engine.POSTINGS_CHANNELS]


def load_country(con, country: str, limit: int) -> dict:
    cols = ', '.join(engine.FEATURE_COLUMNS)
    derived = ', '.join(f'{expr} AS {name}' for name, expr in engine.DERIVED.items())
    q_glob = (FEATURES / 'source=1' / f'country={country}' / '*.parquet').as_posix()
    t_glob = (FEATURES / 'source=[23]' / f'country={country}' / '*.parquet').as_posix()
    limit_sql = f'ORDER BY entity_id LIMIT {limit}' if limit else 'ORDER BY entity_id'
    con.execute(f"""CREATE OR REPLACE TEMP TABLE bq AS
        SELECT row_number() OVER (ORDER BY entity_id)::INT AS qid, {cols}, {derived}
        FROM (SELECT {cols} FROM read_parquet('{q_glob}', hive_partitioning=false) {limit_sql})""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE tt AS
        SELECT row_number() OVER (ORDER BY entity_id)::INT AS tid, {cols}, {derived}
        FROM (SELECT {cols} FROM read_parquet('{t_glob}', hive_partitioning=false))""")
    con.execute("CREATE OR REPLACE TEMP TABLE cand (channel VARCHAR, qid INT, tid INT, rnk INT, score DOUBLE, blk INT)")
    con.execute("CREATE OR REPLACE TEMP TABLE chan_stats (channel VARCHAR, seconds DOUBLE, pairs_before_cap BIGINT, oversize_blocks BIGINT, note VARCHAR)")
    return {'queries': con.execute('SELECT count(*) FROM bq').fetchone()[0], 'targets': con.execute('SELECT count(*) FROM tt').fetchone()[0]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--memory', default='10GB')
    parser.add_argument('--sparse-k', type=int, default=20)
    parser.add_argument('--limit-per-country', type=int, default=0, help='debug only: cap the number of queries per country (0 = all)')
    parser.add_argument('--countries', default='', help='comma-separated subset (default: every country found in test_source1)')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET threads={args.threads}; SET memory_limit='{args.memory}'")
    q_all = (FEATURES / 'source=1' / 'country=*' / '*.parquet').as_posix()
    countries = args.countries.split(',') if args.countries else [r[0] for r in con.execute(f"SELECT DISTINCT country FROM read_parquet('{q_all}', hive_partitioning=false) ORDER BY 1").fetchall()]
    print(f'countries: {countries}', flush=True)
    info = {'sparse_k': args.sparse_k, 'countries': {}}
    started = time.perf_counter()
    for country in countries:
        t0 = time.perf_counter()
        sizes = load_country(con, country, args.limit_per_country)
        print(f'[{country}] {sizes} loaded in {time.perf_counter() - t0:.0f}s; running channels', flush=True)
        engine.run_all_channels(con, log=lambda m: print(m, flush=True))
        out = OUT / f'candidates_{country}.parquet'
        sparse_list = "'" + "', '".join(SPARSE_NAMES) + "'"
        con.execute(f"""COPY (SELECT c.channel, q.entity_id AS q, t.entity_id AS t, c.rnk, c.score, c.blk FROM cand c JOIN bq q USING (qid) JOIN tt t USING (tid)
                         WHERE c.channel NOT IN ({sparse_list}) OR c.rnk <= {args.sparse_k}
                         ORDER BY channel, q, rnk) TO '{out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
        n = con.execute(f"SELECT count(DISTINCT (q, t)) FROM read_parquet('{out.as_posix()}')").fetchone()[0]
        stats = con.execute('SELECT * FROM chan_stats').fetchall()
        info['countries'][country] = {**sizes, 'distinct_pairs': n, 'seconds': time.perf_counter() - t0,
                                      'channel_stats': [dict(zip(['channel', 'seconds', 'pairs_before_cap', 'oversize_blocks', 'note'], r)) for r in stats]}
        print(f'[{country}] {n:,} distinct candidate pairs in {time.perf_counter() - t0:.0f}s', flush=True)
    info['total_seconds'] = time.perf_counter() - started
    (OUT / 'test_candidates_manifest.json').write_text(json.dumps(info, indent=2, default=float) + '\n', encoding='utf-8', newline='\n')
    print(f'done in {info["total_seconds"]:.0f}s', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
