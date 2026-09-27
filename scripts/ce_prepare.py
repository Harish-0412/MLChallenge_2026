"""Cross-encoder step 1 (CPU env): choose the pairs a cross-encoder should see and attach their raw text.

    python scripts/ce_prepare.py --train train50k --val val20k --model xgb_ranker_v1

The cross-encoder only re-ranks the TOP-N first-stage candidates of each query (N = 20).  Using the first-stage classifier's calibrated probability, this writes
    data/benchmarks/ce_train.parquet   fit queries: all true links among the top-N plus their top-N non-links (the confusions the classifier finds plausible)
    data/benchmarks/ce_cal.parquet     calibration queries (the split used for isotonic calibration, disjoint from fit): all top-N pairs (to fit the blend)
    data/benchmarks/ce_val.parquet     validation queries: all top-N pairs
Columns: q, t, label, p_gbdt, rank, split, q_text, t_text.  The text is 'business name | business address' as delivered (raw, not cleaned).
"""
import argparse
import pickle
import sys
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

import train_ranker as tr  # noqa: E402
from ranking import model as rm  # noqa: E402
from ranking import pairs as rp  # noqa: E402

BENCH = ROOT / 'data' / 'benchmarks'
TOP_N = 20


def top_rows(qcode, prob, n):
    order = rm.sort_by_query(qcode, prob)
    q = qcode[order]
    b = np.flatnonzero(np.r_[True, q[1:] != q[:-1], True])
    rank = np.arange(len(q)) - np.repeat(b[:-1], np.diff(b))
    keep = rank < n
    return order[keep], rank[keep] + 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--train', default='train50k')
    parser.add_argument('--val', default='val20k')
    parser.add_argument('--model', default='xgb_ranker_v1')
    args = parser.parse_args()
    from xgboost import XGBClassifier
    model = XGBClassifier()
    model.load_model(str(ROOT / 'data' / 'models_ranker' / f'{args.model}.json'))
    iso = pickle.loads((ROOT / 'data' / 'models_ranker' / ('isotonic_v1.pkl' if args.model == 'xgb_ranker_v1' else f'{args.model}_isotonic.pkl')).read_bytes())
    out = []
    for name, splits in ((args.train, ('fit', 'cal')), (args.val, ('val',))):
        D = tr.load(name, rp.MODEL_FEATURES)
        prob = np.empty(len(D['y']))
        for s in range(0, len(prob), 2_000_000):
            prob[s:s + 2_000_000] = model.predict_proba(D['X'][s:s + 2_000_000])[:, 1]
        prob = iso.predict(prob)
        if name == args.train:
            bucket = np.array([rm.stable_bucket(i, tr.SALT) for i in D['ids']])
            role = np.where(bucket < 80, 'fit', np.where(bucket < 90, 'es', 'cal'))
        else:
            role = np.array(['val'] * len(D['ids']))
        rows, rank = top_rows(D['code'], prob, TOP_N)
        row_split = role[D['code'][rows]]
        keep = np.isin(row_split, splits)
        rows, rank, row_split = rows[keep], rank[keep], row_split[keep]
        out.append(pa.table({'q': D['ids'][D['code'][rows]], 't': D['target'][rows], 'label': D['y'][rows].astype(np.int8), 'p_gbdt': prob[rows], 'rank': rank.astype(np.int32),
                             'split': row_split}))
        print(f'{name}: kept {len(rows):,} pairs of {len(prob):,} (top {TOP_N} per query, splits {splits})', flush=True)
        del D
    table = pa.concat_tables(out)
    con = duckdb.connect()
    con.register('pairs', table)
    glob = (ROOT / 'data' / 'features' / 'feat_v2_0' / 'split=train' / 'source=*' / 'country=*' / '*.parquet').as_posix()
    con.execute(f"""CREATE TABLE ent AS SELECT entity_id, business_name || ' | ' || business_address AS txt FROM read_parquet('{glob}', hive_partitioning=false)
                    WHERE entity_id IN (SELECT q FROM pairs UNION SELECT t FROM pairs)""")
    res = con.execute("SELECT p.q, p.t, p.label, p.p_gbdt, p.rank, p.split, a.txt AS q_text, b.txt AS t_text FROM pairs p JOIN ent a ON a.entity_id = p.q JOIN ent b ON b.entity_id = p.t").fetch_arrow_table()
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    for split, fname in (('fit', 'ce_train'), ('cal', 'ce_cal'), ('val', 'ce_val')):
        t = res.filter(pc.equal(res['split'], split))
        pq.write_table(t, (BENCH / f'{fname}.parquet').as_posix(), compression='zstd')
        print(fname, t.num_rows, 'positives', int(pc.sum(t['label']).as_py()), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
