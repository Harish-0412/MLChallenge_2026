"""Model phase 7: does the one-owner rule (a target belongs to at most one Source-1 entity) cut false matches?

    python scripts/one_owner_experiment.py --mini mini --sparse val20k

Two settings: the MINI-WORLD (complete competition: every target's owner is among the queries; see scripts/build_miniworld.py) and the sparse validation sample (9% of the validation queries,
so most competitors are missing: a lower bound of the benefit).  For each rule variant the policy (tau, top-k) is tuned on half the queries (A) and the macro-F0.5 is reported on
the other half (B).  The frozen first-stage classifier and calibrator are used unchanged.
"""
import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

import train_ranker as tr  # noqa: E402
from ranking import model as rm  # noqa: E402
from ranking import owner  # noqa: E402
from ranking import pairs as rp  # noqa: E402

OUT = ROOT / 'reports' / 'eda'
TAUS = np.round(np.arange(0.05, 0.96, 0.05), 2)
TOPKS = (1, 2, 3, 5, 8, 12)
VARIANTS = [('no rule (baseline)', None, 0.0)] + [(f'one owner, competitors = all candidates, margin {m}', 'all', m) for m in (0.0, 0.1, 0.2, 0.3)] + \
           [(f'one owner, competitors = selected pairs, margin {m}', 'selected', m) for m in (0.0, 0.1)]


def run_setting(name: str, salt: str) -> dict:
    from xgboost import XGBClassifier
    model = XGBClassifier()
    model.load_model(str(ROOT / 'data' / 'models_ranker' / 'xgb_ranker_v1.json'))
    iso = pickle.loads((ROOT / 'data' / 'models_ranker' / 'isotonic_v1.pkl').read_bytes())
    tr.ensure_pairs(name, False)
    D = tr.load(name, rp.MODEL_FEATURES)
    prob = iso.predict(model.predict_proba(D['X'])[:, 1])
    tcode = owner.encode_targets(D['target'])
    is_a = np.array([rm.stable_bucket(i, salt) for i in D['ids']]) < 50
    rows_a, rows_b = is_a[D['code']], ~is_a[D['code']]

    def sub(mask_rows, mask_q):
        idx = np.flatnonzero(mask_q)
        remap = -np.ones(len(mask_q), dtype=int)
        remap[idx] = np.arange(len(idx))
        return remap[D['code'][mask_rows]], D['y'][mask_rows], D['n_true'][idx]
    qa, ya, na = sub(rows_a, is_a)
    qb, yb, nb = sub(rows_b, ~is_a)
    out = {'queries': int(len(D['ids'])), 'pairs': int(len(D['y'])), 'distinct_targets': int(tcode.max() + 1), 'variants': []}
    # how many targets are candidates of more than one query (the competition that the rule can use)?
    per_t = np.bincount(tcode)
    out['share_of_pairs_on_contested_targets'] = float((per_t[tcode] > 1).mean())
    for label, among, margin in VARIANTS:
        best, best_score = None, -1.0
        for tau in TAUS:
            for k in TOPKS:
                sel = rm.select_threshold(qa, prob[rows_a], tau, k)
                if among:
                    sel = owner.apply_one_owner(sel, tcode[rows_a], qa, prob[rows_a], margin, among)
                s = rm.macro_f05_from_selection(qa, ya, sel, na)
                if s > best_score + 1e-12:
                    best, best_score = {'tau': float(tau), 'top_k': k}, s
        sel_b = rm.select_threshold(qb, prob[rows_b], best['tau'], best['top_k'])
        if among:
            sel_b = owner.apply_one_owner(sel_b, tcode[rows_b], qb, prob[rows_b], margin, among)
        per_q = rm.macro_f05_from_selection(qb, yb, sel_b, nb, per_query=True)
        out['variants'].append({'variant': label, 'val_A': best_score, 'val_B': float(per_q.mean()), 'policy': best, 'tp': int((sel_b & (yb == 1)).sum()), 'fp': int((sel_b & (yb == 0)).sum()),
                                'singleton_fp_rate': float(np.mean(per_q[nb == 0] == 0))})
        print(f"{name}: {label}: A {best_score:.4f} B {per_q.mean():.4f} TP {out['variants'][-1]['tp']} FP {out['variants'][-1]['fp']}", flush=True)
    base = out['variants'][0]
    out['best_by_val_A'] = max(out['variants'], key=lambda v: v['val_A'])['variant']
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--mini', default='mini')
    parser.add_argument('--sparse', default='val20k')
    args = parser.parse_args()
    result = {'mini_world': run_setting(args.mini, 'owner-mini'), 'sparse_validation': run_setting(args.sparse, tr.SALT + '-val')}
    (OUT / 'one_owner_results.json').write_text(json.dumps(result, indent=2, default=float) + '\n', encoding='utf-8', newline='\n')
    md = ['# One-owner rule (model phase 7)', '', 'Rule: a target selected for several queries is kept only for its most probable owner (competitors: all candidate pairs, or only selected pairs), optionally with a probability margin. '
          'Policy (tau, top-k) tuned on half the queries (A) per variant, reported on the other half (B). Frozen classifier; no holdout.', '']
    for setting, title in (('mini_world', 'Mini-world: complete competition (10% of validation queries with all their owned targets; corpus 10x smaller, so absolute scores are optimistic)'),
                           ('sparse_validation', 'Sparse validation sample (9% of validation queries; most competitors absent: lower bound of the benefit)')):
        r = result[setting]
        md += [f'## {title}', '', f"{r['queries']:,} queries, {r['pairs']:,} pairs, {r['distinct_targets']:,} distinct targets; {100 * r['share_of_pairs_on_contested_targets']:.1f}% of pairs are on targets that are a candidate of more than one query.", '',
               '| variant | val-A | **val-B** | TP | FP | singleton FP rate |', '|---|---:|---:|---:|---:|---:|']
        md += [f"| {v['variant']} | {v['val_A']:.4f} | **{v['val_B']:.4f}** | {v['tp']:,} | {v['fp']:,} | {100 * v['singleton_fp_rate']:.2f}% |" for v in r['variants']]
        md += ['', f"Best by val-A: {r['best_by_val_A']}.", '']
    (OUT / 'one_owner_results.md').write_text('\n'.join(md) + '\n', encoding='utf-8', newline='\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
