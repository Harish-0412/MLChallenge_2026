"""Rebuild the India candidates with a different thread count and require the identical candidate set (rank, score) as the frozen file.

    python scripts/retrieval_determinism_check.py
"""
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from retrieval import engine  # noqa: E402

MANIFEST = (ROOT / 'data' / 'splits' / 'fold_manifest_v1.parquet').as_posix()
FROZEN = (ROOT / 'data' / 'benchmarks' / 'candidates_dev10k_v1.parquet').as_posix()
COUNTRY = 'India'


def main() -> int:
    started = time.perf_counter()
    con = duckdb.connect()
    con.execute("SET threads=3; SET memory_limit='9GB'")
    con.execute(f"CREATE TEMP TABLE bench_q AS SELECT * FROM read_parquet('{(ROOT / 'data' / 'benchmarks' / 'bench_dev10k_v1.parquet').as_posix()}')")
    glob = (ROOT / 'data' / 'features' / 'feat_v2_0' / 'split=train' / 'source=*' / f'country={COUNTRY}' / '*.parquet').as_posix()
    engine.load_corpus(con, glob, MANIFEST, COUNTRY)
    engine.run_all_channels(con, log=lambda m: None)
    con.execute("""CREATE TEMP TABLE rebuilt AS SELECT c.channel, q.entity_id AS q, t.entity_id AS t, c.rnk, c.score FROM cand c JOIN bq q USING (qid) JOIN tt t USING (tid)""")
    frozen = f"(SELECT * FROM read_parquet('{FROZEN}') WHERE q IN (SELECT id FROM bench_q WHERE country = '{COUNTRY}'))"
    only_new = con.execute(f"SELECT count(*) FROM (SELECT * FROM rebuilt EXCEPT SELECT * FROM {frozen})").fetchone()[0]
    only_old = con.execute(f"SELECT count(*) FROM (SELECT * FROM {frozen} EXCEPT SELECT * FROM rebuilt)").fetchone()[0]
    n = con.execute('SELECT count(*) FROM rebuilt').fetchone()[0]
    print(f'{COUNTRY}: rebuilt {n:,} candidate rows with 3 threads; rows only in rebuild {only_new}, only in frozen file {only_old} ({time.perf_counter() - started:.0f}s)')
    return 0 if only_new == 0 and only_old == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
