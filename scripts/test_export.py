"""Score the real test candidates with the frozen classifier and write the two submission files.

    python scripts/test_export.py [--shards 24] [--workers 24] [--memory 40GB] [--shard-memory 4GB] [--tau 0.7] [--top-k 12] [--limit 0]

Pipeline: data/test_output/candidates_<country>.parquet (from scripts/test_candidates.py, features only, no label) ->
candidate_v1 (is_positive = -1, no truth) -> pair features (ranking.pairs.build_pairs, sharded) -> XGBoost + isotonic calibration (frozen, trained
only on training-fold data) -> per-query decision policy -> output/matching_results.tsv and output/candidate_pairs.tsv.

The decision policy (tau, top_k) defaults to the one tuned on protocol-B (full 10.3M-target training corpus) validation queries -
reports/eda/fullcorpus_valfull5k.json, variant (ii) - because that is the density the real test corpus matches; override with --tau/--top-k if you
disagree. Every test Source-1 entity gets exactly one row in both files, including entities with no candidates (empty string).
"""
import argparse
import csv
import json
import pickle
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from ranking import model as rm  # noqa: E402
from ranking import pairs as rp  # noqa: E402

TEST_OUT = ROOT / 'data' / 'test_output'
FEATURE_ROOT = ROOT / 'data' / 'features' / 'feat_v2_0'
TEST_SOURCE1 = (ROOT / 'data' / 'features' / 'feat_v2_0' / 'split=test' / 'source=1').as_posix()
MODELS = ROOT / 'data' / 'models_ranker'
OUT_DIR = ROOT / 'output'
DEFAULT_TAU, DEFAULT_TOP_K = 0.7, 12    # reports/eda/fullcorpus_valfull5k.json, policy variant (ii): tuned on protocol-B (full-corpus) val-A queries


def write_tsv(path: Path, rows: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['source1_entity_id', 'matched_entity_ids' if 'matching' in path.name else 'candidate_entity_ids'])
        for q in sorted(rows):
            w.writerow([q, ','.join(rows[q])])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--shards', type=int, default=8)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--memory', default='16GB')
    parser.add_argument('--shard-memory', default='2500MB')
    parser.add_argument('--tau', type=float, default=DEFAULT_TAU)
    parser.add_argument('--top-k', type=int, default=DEFAULT_TOP_K)
    parser.add_argument('--margin', type=float, default=0.0)
    parser.add_argument('--model', default='xgb_ranker_v1')
    parser.add_argument('--limit', type=int, default=0, help='debug only: process at most this many candidate pairs')
    parser.add_argument('--resume', action='store_true', help='reuse _candidates_all/_candidate_v1/_pairs.parquet from data/test_output if already present, '
                        'instead of rebuilding them (use after a crash past the step you want to keep; each stage still checks its own row counts)')
    args = parser.parse_args()
    started = time.perf_counter()
    con = duckdb.connect()
    con.execute(f"SET threads={args.workers}; SET memory_limit='{args.memory}'")

    cand_glob = (TEST_OUT / 'candidates_*.parquet').as_posix()
    cand_all = TEST_OUT / '_candidates_all.parquet'
    if args.resume and cand_all.exists():
        print(f'resume: reusing existing {cand_all.name}', flush=True)
    else:
        if cand_all.exists():
            cand_all.unlink()
        limit_sql = f'LIMIT {args.limit}' if args.limit else ''
        con.execute(f"COPY (SELECT * FROM read_parquet('{cand_glob}') {limit_sql}) TO '{cand_all.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    n_pairs_raw, n_q_with_cand = con.execute(f"SELECT count(DISTINCT (q, t)), count(DISTINCT q) FROM read_parquet('{cand_all.as_posix()}')").fetchone()
    print(f'raw candidate rows: {n_pairs_raw:,} distinct pairs over {n_q_with_cand:,} queries with at least one candidate ({time.perf_counter() - started:.0f}s)', flush=True)

    queries_file = TEST_OUT / '_queries_all.parquet'
    if args.resume and queries_file.exists():
        print(f'resume: reusing existing {queries_file.name}', flush=True)
    else:
        con.execute(f"""COPY (SELECT entity_id AS id, country FROM read_parquet('{(TEST_SOURCE1 + "/country=*/*.parquet")}', hive_partitioning=false))
                        TO '{queries_file.as_posix()}' (FORMAT PARQUET)""")
    n_required = con.execute(f"SELECT count(*) FROM read_parquet('{queries_file.as_posix()}')").fetchone()[0]
    print(f'required Source-1 entities: {n_required:,}', flush=True)

    cand_v1 = TEST_OUT / '_candidate_v1.parquet'
    if args.resume and cand_v1.exists():
        info = con.execute(f"SELECT count(*), count(DISTINCT s1_entity_id), sum(is_positive = 1) FROM read_parquet('{cand_v1.as_posix()}')").fetchone()
        info = {'pairs': info[0], 'queries_with_candidates': info[1], 'positives': int(info[2] or 0)}
        print(f'resume: reusing existing {cand_v1.name}: {info}', flush=True)
    else:
        if cand_v1.exists():
            cand_v1.unlink()
        info = rp.aggregate_candidates(cand_all.as_posix(), queries_file.as_posix(), cand_v1.as_posix(), threads=args.workers, memory=args.memory)
        print(f'candidate_v1: {info} ({time.perf_counter() - started:.0f}s)', flush=True)

    pairs_file = TEST_OUT / '_pairs.parquet'
    if args.resume and pairs_file.exists():
        n_pairs_built = con.execute(f"SELECT count(*) FROM read_parquet('{pairs_file.as_posix()}')").fetchone()[0]
        if n_pairs_built != info['pairs']:
            raise RuntimeError(f'resume: {pairs_file.name} has {n_pairs_built:,} rows but candidate_v1 has {info["pairs"]:,}; rerun without --resume')
        print(f'resume: reusing existing {pairs_file.name} ({n_pairs_built:,} rows, matches candidate_v1)', flush=True)
    else:
        if pairs_file.exists():
            pairs_file.unlink()
        res = rp.build_pairs(cand_all.as_posix(), cand_v1.as_posix(), FEATURE_ROOT.as_posix(), pairs_file.as_posix(), (TEST_OUT / '_work').as_posix(),
                             threads=args.workers, shards=args.shards, workers=args.workers, memory=args.memory, shard_memory=args.shard_memory, validate=False)
        print(f'pair features: {res} ({time.perf_counter() - started:.0f}s)', flush=True)

    from xgboost import XGBClassifier
    model = XGBClassifier()
    model.load_model(str(MODELS / f'{args.model}.json'))
    iso_name = 'isotonic_v1.pkl' if args.model == 'xgb_ranker_v1' else f'{args.model.replace("xgb_ranker_", "isotonic_")}.pkl'
    iso = pickle.loads((MODELS / iso_name).read_bytes())
    table = pq.read_table(pairs_file)
    q_ids = table.column('s1_entity_id').to_numpy(zero_copy_only=False)
    t_ids = table.column('candidate_entity_id').to_numpy(zero_copy_only=False)
    X = np.column_stack([table.column(f).to_numpy(zero_copy_only=False) for f in rp.assert_model_features(rp.MODEL_FEATURES)]).astype(np.float32)
    del table
    prob = np.empty(len(X), dtype=np.float64)
    for s in range(0, len(X), 2_000_000):
        prob[s:s + 2_000_000] = iso.predict(model.predict_proba(X[s:s + 2_000_000])[:, 1])
    del X
    print(f'scored {len(prob):,} pairs ({time.perf_counter() - started:.0f}s)', flush=True)

    order = np.argsort(q_ids, kind='stable')
    q_sorted, t_sorted, p_sorted = q_ids[order], t_ids[order], prob[order]
    uniq_q, qcode = np.unique(q_sorted, return_inverse=True)
    sel = rm.select_threshold(qcode, p_sorted, args.tau, args.top_k, args.margin)
    print(f'policy tau={args.tau} top_k={args.top_k} margin={args.margin}: {int(sel.sum()):,} of {len(sel):,} candidates selected', flush=True)

    candidates_by_q, matches_by_q = {}, {}
    for i in range(len(q_sorted)):
        candidates_by_q.setdefault(q_sorted[i], []).append(t_sorted[i])
    for i in np.flatnonzero(sel):
        matches_by_q.setdefault(q_sorted[i], []).append(t_sorted[i])
    required = con.execute(f"SELECT id FROM read_parquet('{queries_file.as_posix()}')").fetchall()
    for (q,) in required:
        candidates_by_q.setdefault(q, [])
        matches_by_q.setdefault(q, [])
    for q, lst in candidates_by_q.items():
        assert len(set(lst)) == len(lst), f'duplicate candidate for {q}'
    for q, lst in matches_by_q.items():
        assert len(set(lst)) == len(lst), f'duplicate match for {q}'
        assert set(lst) <= set(candidates_by_q[q]), f'{q}: a selected match is not among its candidates'
    write_tsv(OUT_DIR / 'matching_results.tsv', matches_by_q)
    write_tsv(OUT_DIR / 'candidate_pairs.tsv', candidates_by_q)
    empty = sum(1 for v in matches_by_q.values() if not v)
    print(f'wrote {len(matches_by_q):,} rows to matching_results.tsv ({empty:,} empty) and candidate_pairs.tsv', flush=True)
    print(f'mean candidates/query: {sum(len(v) for v in candidates_by_q.values()) / len(candidates_by_q):.1f}; '
          f'mean matches/query: {sum(len(v) for v in matches_by_q.values()) / len(matches_by_q):.3f}', flush=True)
    print(f'done in {time.perf_counter() - started:.0f}s', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
