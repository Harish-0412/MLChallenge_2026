"""Union an embedding-channel candidate file into a candidate set, under the name <name>E (queries file copied).

    python scripts/merge_emb.py --name train50k [--emb val20kS]
"""
import argparse
import shutil
import sys
from pathlib import Path

import duckdb

BENCH = Path(__file__).resolve().parents[1] / 'data' / 'benchmarks'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    parser.add_argument('--emb', default='', help='embedding candidate set name (default: same as --name)')
    args = parser.parse_args()
    emb = BENCH / f'cand_{args.emb or args.name}_emb.parquet'
    con = duckdb.connect()
    con.execute("SET threads=6; SET memory_limit='8GB'")
    out = BENCH / f'cand_{args.name}E.parquet'
    con.execute(f"""COPY (SELECT channel, q, t, rnk, score, blk FROM read_parquet('{(BENCH / f'cand_{args.name}.parquet').as_posix()}')
                          UNION ALL SELECT channel, q, t, rnk, score, blk FROM read_parquet('{emb.as_posix()}')) TO '{out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    shutil.copy(BENCH / f'queries_{args.name}.parquet', BENCH / f'queries_{args.name}E.parquet')
    n_new = con.execute(f"""SELECT count(*) FROM (SELECT DISTINCT q, t FROM read_parquet('{emb.as_posix()}') EXCEPT SELECT DISTINCT q, t FROM read_parquet('{(BENCH / f'cand_{args.name}.parquet').as_posix()}'))""").fetchone()[0]
    print(f'{out.name}: pairs found only by the embedding channel: {n_new:,}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
