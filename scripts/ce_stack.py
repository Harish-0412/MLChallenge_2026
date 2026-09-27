"""Cross-encoder step 3 (CPU env): blend the cross-encoder logit with the first-stage probability and compare with the first stage alone, end to end.

    python scripts/ce_stack.py

The blend (logistic regression on [logit(p_gbdt), ce_logit, 1/rank]) is fitted on the calibration queries; the policy is tuned on val-A and the score is reported on
val-B, exactly as for the classifier.  Only the top-20 first-stage candidates of each query can be selected in both arms (the same restriction), so the comparison is fair.
Verdict rule (from the plan): keep the cross-encoder only if val-B macro-F0.5 improves by more than the sampling noise (reported as a paired bootstrap 95% interval).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

import train_ranker as tr  # noqa: E402
from ranking import model as rm  # noqa: E402

BENCH = ROOT / 'data' / 'benchmarks'
OUT = ROOT / 'reports' / 'eda'
TAUS = np.round(np.arange(0.05, 0.96, 0.05), 2)


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def main() -> int:
    from sklearn.linear_model import LogisticRegression
    scores = pq.read_table(BENCH / 'ce_scores.parquet').to_pydict()
    ce = {(q, t): s for q, t, s in zip(scores['q'], scores['t'], scores['ce_logit'])}
    cal = pq.read_table(BENCH / 'ce_cal.parquet').to_pydict()
    val = pq.read_table(BENCH / 'ce_val.parquet').to_pydict()
    Xc = np.column_stack([logit(np.array(cal['p_gbdt'])), [ce[(q, t)] for q, t in zip(cal['q'], cal['t'])], 1.0 / np.array(cal['rank'])])
    yc = np.array(cal['label'])
    blend = LogisticRegression(C=10.0, max_iter=1000).fit(Xc, yc)
    Xv = np.column_stack([logit(np.array(val['p_gbdt'])), [ce[(q, t)] for q, t in zip(val['q'], val['t'])], 1.0 / np.array(val['rank'])])
    p_gb = np.array(val['p_gbdt'])
    p_bl = blend.predict_proba(Xv)[:, 1]
    yv = np.array(val['label'], dtype=np.int8)
    queries = pq.read_table(BENCH / 'queries_val20k.parquet').to_pydict()
    order = np.argsort(np.array(queries['id']))
    ids = np.array(queries['id'])[order]
    n_true = np.array(queries['match_count'], dtype=float)[order]
    code = np.searchsorted(ids, np.array(val['q']))
    val_a = np.array([rm.stable_bucket(i, tr.SALT + '-val') for i in ids]) < 50

    def evaluate(prob):
        def sub(mask_q):
            idx = np.flatnonzero(mask_q)
            remap = -np.ones(len(mask_q), dtype=int)
            remap[idx] = np.arange(len(idx))
            rows = mask_q[code]
            return remap[code[rows]], yv[rows], prob[rows], n_true[idx], rows
        qa, ya, pa_, na, ra = sub(val_a)
        qb, yb, pb_, nb, rb = sub(~val_a)
        best, score_a = rm.search_threshold_policy(qa, pa_, ya, na, TAUS, (1, 2, 3, 5, 8, 12))
        sel = rm.select_threshold(qb, pb_, best['tau'], best['top_k'], best['margin'])
        per_q = rm.macro_f05_from_selection(qb, yb, sel, nb, per_query=True)
        return per_q, {'policy': best, 'val_A': score_a, 'val_B': float(per_q.mean()), 'tp': int((sel & (yb == 1)).sum()), 'fp': int((sel & (yb == 0)).sum())}
    pq_gb, r_gb = evaluate(p_gb)
    pq_bl, r_bl = evaluate(p_bl)
    diff = pq_bl - pq_gb
    rng = np.random.default_rng(1)
    boots = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(2000)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    keep = lo > 0
    result = {'first_stage_top20': r_gb, 'blend_top20': r_bl, 'paired_difference_val_B': float(diff.mean()), 'bootstrap_95': [float(lo), float(hi)], 'keep_cross_encoder': bool(keep),
              'blend_coefficients': [float(c) for c in blend.coef_[0]] + [float(blend.intercept_[0])], 'val_B_queries': int(len(diff))}
    (OUT / 'cross_encoder_results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    md = ['# Cross-encoder reranker (multilingual-e5-small, MIT) vs the first-stage classifier', '',
          'Both arms select only among the first-stage top-20 candidates; policy tuned on val-A; val-B reported; paired bootstrap over val-B queries.', '',
          '| arm | val-A | val-B | TP | FP |', '|---|---:|---:|---:|---:|',
          f"| first stage (XGBoost, calibrated) | {r_gb['val_A']:.4f} | {r_gb['val_B']:.4f} | {r_gb['tp']:,} | {r_gb['fp']:,} |",
          f"| + cross-encoder blend | {r_bl['val_A']:.4f} | {r_bl['val_B']:.4f} | {r_bl['tp']:,} | {r_bl['fp']:,} |", '',
          f"Paired difference on val-B: {diff.mean():+.5f} (95% bootstrap interval {lo:+.5f} .. {hi:+.5f}); verdict: **{'keep' if keep else 'drop (no significant gain)'}**."]
    (OUT / 'cross_encoder_results.md').write_text('\n'.join(md) + '\n', encoding='utf-8', newline='\n')
    print('\n'.join(md))
    return 0


if __name__ == '__main__':
    sys.exit(main())
