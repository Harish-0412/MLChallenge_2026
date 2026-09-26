"""Generate a candidate set (all channels of src/retrieval) for a deterministic sample of queries, features only (no label is read).

    python scripts/build_candidate_set.py --name train50k --query-fold dev --corpus-fold dev --queries 50000
    python scripts/build_candidate_set.py --name val20k   --query-fold val --corpus-fold val --queries 20000
    python scripts/build_candidate_set.py --name valfull5k --query-fold val --corpus-fold all --queries 5000 --fullcorpus-only

``--corpus-fold dev|val|holdout`` is protocol A (isolated fold); ``all`` is protocol B (the complete training target corpus, the size the test
faces). Outputs: data/benchmarks/queries_<name>.parquet, cand_<name>.parquet (channel, q, t, rnk, score, blk), cand_<name>.json (digest, sizes, timings).
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from retrieval import engine  # noqa: E402

MANIFEST = (ROOT / 'data' / 'splits' / 'fold_manifest_v1.parquet').as_posix()
FEATURES = ROOT / 'data' / 'features' / 'feat_v2_0'
BENCH = ROOT / 'data' / 'benchmarks'
COUNTRIES = ('India', 'US')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--name', required=True)
    parser.add_argument('--query-fold', default='dev', choices=['dev', 'val', 'holdout'])
    parser.add_argument('--corpus-fold', default='dev', choices=['dev', 'val', 'holdout', 'all'])
    parser.add_argument('--queries', type=int, default=10_000)
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--fullcorpus-only', action='store_true', help='sample only the queries flagged fullcorpus_sample in the manifest')
    args = parser.parse_args()
    if args.query_fold == 'holdout':
        print('refusing: the locked holdout is only used for frozen versions (see validation_protocol.md)', file=sys.stderr)
        return 2
    started = time.perf_counter()
    BENCH.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET threads={args.threads}; SET memory_limit='10GB'")
    manifest = MANIFEST
    if args.fullcorpus_only:
        con.execute(f"CREATE TEMP TABLE _m AS SELECT * FROM read_parquet('{MANIFEST}') WHERE role = 'query' AND fullcorpus_sample")
        manifest = (BENCH / '_fullcorpus_queries.parquet').as_posix()
        con.execute(f"COPY _m TO '{manifest}' (FORMAT PARQUET)")
    digest = engine.sample_queries(con, manifest, args.queries, seed=f'{engine.SEED}-{args.name}', fold=args.query_fold, table='qset')
    con.execute(f"COPY (SELECT * FROM qset ORDER BY id) TO '{(BENCH / f'queries_{args.name}.parquet').as_posix()}' (FORMAT PARQUET)")
    print(args.name, 'queries', con.execute('SELECT country, count(*) FROM qset GROUP BY 1 ORDER BY 1').fetchall(), 'digest', digest[:16], flush=True)
    corpus_fold = None if args.corpus_fold == 'all' else args.corpus_fold
    parts, sizes, stats = [], {}, []
    for country in COUNTRIES:
        t0 = time.perf_counter()
        glob = (FEATURES / 'split=train' / 'source=*' / f'country={country}' / '*.parquet').as_posix()
        sizes[country] = engine.load_corpus(con, glob, MANIFEST, country, fold=corpus_fold, queries='qset')
        print(f'[{country}] {sizes[country]} loaded in {time.perf_counter() - t0:.0f}s', flush=True)
        engine.run_all_channels(con, log=lambda m: print(m, flush=True))
        part = (BENCH / f'_c_{args.name}_{country}.parquet').as_posix()
        con.execute(f"""COPY (SELECT c.channel, q.entity_id AS q, t.entity_id AS t, c.rnk, c.score, c.blk FROM cand c JOIN bq q USING (qid) JOIN tt t USING (tid)
                         ORDER BY channel, q, rnk) TO '{part}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
        parts.append(part)
        stats += [dict(zip(['channel', 'seconds', 'pairs_before_cap', 'oversize_query_blocks', 'note'], r), country=country) for r in con.execute('SELECT * FROM chan_stats').fetchall()]
        print(f'[{country}] done in {time.perf_counter() - t0:.0f}s', flush=True)
    final = BENCH / f'cand_{args.name}.parquet'
    con.execute(f"COPY (SELECT * FROM read_parquet([{', '.join(repr(p) for p in parts)}]) ORDER BY channel, q, rnk) TO '{final.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    for p in parts:
        Path(p).unlink()
    rows = con.execute(f"SELECT count(*) FROM read_parquet('{final.as_posix()}')").fetchone()[0]
    info = {'name': args.name, 'query_fold': args.query_fold, 'corpus_fold': args.corpus_fold, 'query_digest': digest, 'corpus': sizes, 'candidate_rows': rows,
            'channel_stats': stats, 'seconds': time.perf_counter() - started}
    (BENCH / f'cand_{args.name}.json').write_text(json.dumps(info, indent=2, default=float) + '\n', encoding='utf-8', newline='\n')
    print(f'{args.name}: {rows:,} candidate rows in {time.perf_counter() - started:.0f}s', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
