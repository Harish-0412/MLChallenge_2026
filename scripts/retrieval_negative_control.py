"""Negative control for the retrieval benchmark: if recall comes from record content (and not from IDs, tie-breaks or corpus order),
retrieving with the features of the WRONG query must collapse recall to chance.

    python scripts/retrieval_negative_control.py

Each India benchmark query is given the features of another benchmark query (a cyclic shift by 7), the channels run exactly as in the benchmark,
and the result is scored against the ORIGINAL query's true targets. Expected: real recall high, shuffled recall ~ 0.
"""
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from retrieval import engine  # noqa: E402

MANIFEST = (ROOT / 'data' / 'splits' / 'fold_manifest_v1.parquet').as_posix()
BENCH = ROOT / 'data' / 'benchmarks'
FLAGS = (ROOT / 'data' / 'scratch' / 'label_pairs.parquet').as_posix()
COUNTRY = 'India'
CHANNELS = ['eq_name_core', 'bigram_address', 'tok_name']


def recall(con, label):
    links, hits = con.execute(f"""
        WITH tr AS (SELECT p.q, p.t FROM read_parquet('{FLAGS}') p WHERE p.q IN (SELECT entity_id FROM bq)),
             sel AS (SELECT DISTINCT q.entity_id AS q, t.entity_id AS t FROM cand c JOIN bq q USING (qid) JOIN tt t USING (tid))
        SELECT (SELECT count(*) FROM tr), (SELECT count(*) FROM tr JOIN sel USING (q, t))""").fetchone()
    print(f'{label}: recall {hits}/{links} = {100 * hits / links:.2f}%', flush=True)
    return hits / links


def main() -> int:
    started = time.perf_counter()
    con = duckdb.connect()
    con.execute("SET threads=8; SET memory_limit='10GB'")
    con.execute(f"CREATE TEMP TABLE bench_q AS SELECT * FROM read_parquet('{(BENCH / 'bench_dev10k_v1.parquet').as_posix()}')")
    glob = (ROOT / 'data' / 'features' / 'feat_v2_0' / 'split=train' / 'source=*' / f'country={COUNTRY}' / '*.parquet').as_posix()
    engine.load_corpus(con, glob, MANIFEST, COUNTRY)
    specs = {s['name']: s for s in engine.EQUALITY_CHANNELS + engine.POSTINGS_CHANNELS}

    def run():
        con.execute('DELETE FROM cand')
        for name in CHANNELS:
            s = specs[name]
            if 'expr' in s:
                engine.equality_channel(con, name, s['expr'], s['secondary'])
            else:
                engine.postings_channel(con, name, s['tokens'], s['df_cap'], s['rarest'])
        con.execute('DELETE FROM cand WHERE rnk > 20')
    run()
    real = recall(con, 'real features (k<=20)')
    # shift the feature rows across queries but keep each qid's identity
    cols = [c for c in engine.FEATURE_COLUMNS if c != 'entity_id'] + list(engine.DERIVED)
    con.execute(f"CREATE TEMP TABLE bq_real AS SELECT * FROM bq")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE bq AS
        SELECT a.qid, a.entity_id, {', '.join('b.' + c for c in cols)}
        FROM bq_real a JOIN bq_real b ON b.qid = (a.qid + 6) % (SELECT count(*) FROM bq_real) + 1""")
    run()
    shuffled = recall(con, 'features of a different query (control)')
    ok = real > 0.5 and shuffled < 0.02
    print(f'negative control {"PASS" if ok else "FAIL"}: real {real:.4f} vs shuffled {shuffled:.4f} ({time.perf_counter() - started:.0f}s)')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
