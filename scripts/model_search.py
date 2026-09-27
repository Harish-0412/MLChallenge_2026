"""Model phase 5: LightGBM vs XGBoost, a small hyper-parameter search, a hard-negative round and a calibration comparison, all scored on END-TO-END
macro-F0.5 (policy tuned on val-A, reported on val-B) with the same disjoint query groups as scripts/train_ranker.py. The locked holdout is never used.

    python scripts/model_search.py --train train50k --val val20k [--tag v1]

Selection rule: the variant with the best val-A score (policy tuned on val-A, so it is the same optimistic quantity for every variant) is the winner; val-B is reported
for all variants and is what to quote.  Outputs: reports/eda/model_search_<tag>.json/.md and data/models_ranker/best_<tag>.* .
"""
import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

import train_ranker as tr  # noqa: E402
from ranking import model as rm  # noqa: E402
from ranking import pairs as rp  # noqa: E402

OUT = ROOT / 'reports' / 'eda'
MODELS = ROOT / 'data' / 'models_ranker'
TAUS = np.round(np.arange(0.05, 0.96, 0.05), 2)
TOPKS = (1, 2, 3, 5, 8, 12)


def evaluate_scores(prob, D, val_a):
    A_rows, B_rows = val_a[D['code']], ~val_a[D['code']]

    def sub(mask_rows, mask_q):
        idx = np.flatnonzero(mask_q)
        remap = -np.ones(len(mask_q), dtype=int)
        remap[idx] = np.arange(len(idx))
        return remap[D['code'][mask_rows]], D['y'][mask_rows], D['n_true'][idx]
    qa, ya, na = sub(A_rows, val_a)
    qb, yb, nb = sub(B_rows, ~val_a)
    best, score_a = rm.search_threshold_policy(qa, prob[A_rows], ya, na, TAUS, TOPKS)
    sel = rm.select_threshold(qb, prob[B_rows], best['tau'], best['top_k'], best['margin'])
    per_q = rm.macro_f05_from_selection(qb, yb, sel, nb, per_query=True)
    single = nb == 0
    return {'policy': best, 'val_A': score_a, 'val_B': float(per_q.mean()), 'singleton_fp_rate': float(np.mean(per_q[single] == 0)),
            'tp': int((sel & (yb == 1)).sum()), 'fp': int((sel & (yb == 0)).sum())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--train', default='train50k')
    parser.add_argument('--val', default='val20k')
    parser.add_argument('--tag', default='v1')
    parser.add_argument('--features-file', default='', help='optional JSON list of feature names (defaults to ranking.pairs.MODEL_FEATURES)')
    args = parser.parse_args()
    features = json.loads(Path(args.features_file).read_text()) if args.features_file else rp.MODEL_FEATURES
    train, val = tr.load(args.train, features), tr.load(args.val, features)
    bucket = np.array([rm.stable_bucket(i, tr.SALT) for i in train['ids']])
    role = np.where(bucket < 80, 0, np.where(bucket < 90, 1, 2))
    row_role = role[train['code']]
    fit, es, cal = row_role == 0, row_role == 1, row_role == 2
    val_a = np.array([rm.stable_bucket(i, tr.SALT + '-val') for i in val['ids']]) < 50
    Xf, yf, Xe, ye, Xc, yc = train['X'][fit], train['y'][fit], train['X'][es], train['y'][es], train['X'][cal], train['y'][cal]
    results, scores = [], {}

    def run(name, trainer):
        t0 = time.perf_counter()
        predict = trainer()
        raw = predict(val['X'])
        cal_raw = predict(Xc)
        iso = rm.fit_isotonic(cal_raw, yc)
        prob = iso.predict(raw)
        ev = evaluate_scores(prob, val, val_a)
        ev.update({'variant': name, 'seconds': time.perf_counter() - t0})
        results.append(ev)
        scores[name] = (raw, prob, iso, cal_raw)
        print(f"{name}: val-A {ev['val_A']:.4f}  val-B {ev['val_B']:.4f}  policy {ev['policy']}  ({ev['seconds']:.0f}s)", flush=True)

    def xgb(depth, lr=0.1, weights=None, n_est=600):
        def trainer():
            from xgboost import XGBClassifier
            m = XGBClassifier(n_estimators=n_est, learning_rate=lr, max_depth=depth, subsample=0.85, colsample_bytree=0.85, min_child_weight=5.0, reg_lambda=2.0,
                              objective='binary:logistic', eval_metric='logloss', tree_method='hist', early_stopping_rounds=30, n_jobs=8, random_state=20260926)
            m.fit(Xf, yf, sample_weight=weights, eval_set=[(Xe, ye)], verbose=False)
            trainer.model = m
            return lambda X: m.predict_proba(X)[:, 1]
        return trainer

    def lgbm(leaves, lr=0.1):
        def trainer():
            from lightgbm import LGBMClassifier, early_stopping, log_evaluation
            m = LGBMClassifier(n_estimators=800, learning_rate=lr, num_leaves=leaves, subsample=0.85, subsample_freq=1, colsample_bytree=0.85, min_child_weight=5.0,
                               reg_lambda=2.0, objective='binary', n_jobs=8, random_state=20260926, deterministic=True, force_col_wise=True, verbosity=-1)
            m.fit(Xf, yf, eval_set=[(Xe, ye)], callbacks=[early_stopping(30, verbose=False), log_evaluation(0)])
            return lambda X: m.predict_proba(X)[:, 1]
        return trainer

    t_x6 = xgb(6)
    run('xgboost depth 6 (baseline)', t_x6)
    base_model = t_x6.model
    run('xgboost depth 4', xgb(4))
    run('xgboost depth 8', xgb(8))
    run('lightgbm 63 leaves', lgbm(63))
    run('lightgbm 255 leaves', lgbm(255))
    # hard-negative round: up-weight negatives that the round-1 model scores above 0.05 (the ones it finds plausible)
    p_fit = base_model.predict_proba(Xf)[:, 1]
    w = np.where((yf == 0) & (p_fit > 0.05), 3.0, 1.0)
    print(f'hard-negative round: {int(((yf == 0) & (p_fit > 0.05)).sum()):,} negatives up-weighted x3', flush=True)
    run('xgboost depth 6, hard negatives x3 (round 2)', xgb(6, weights=w))
    winner = max(results, key=lambda r: r['val_A'])
    # calibration comparison on the winner's raw scores
    raw, prob, iso, cal_raw = scores[winner['variant']]
    from sklearn.linear_model import LogisticRegression
    platt = LogisticRegression(random_state=0).fit(cal_raw.reshape(-1, 1), yc)
    calib = []
    for label, fn in (('none (raw scores)', lambda r: r), ('Platt (sigmoid)', lambda r: platt.predict_proba(r.reshape(-1, 1))[:, 1]), ('isotonic (used)', lambda r: iso.predict(r))):
        calib.append({'calibration': label, **{k: v for k, v in evaluate_scores(fn(raw), val, val_a).items() if k in ('val_A', 'val_B', 'policy')}})
    print('calibration comparison:', calib, flush=True)
    MODELS.mkdir(parents=True, exist_ok=True)
    (MODELS / f'best_{args.tag}_isotonic.pkl').write_bytes(pickle.dumps(iso))
    payload = {'train': args.train, 'val': args.val, 'variants': results, 'winner_by_val_A': winner['variant'], 'calibration': calib, 'features': len(features)}
    (OUT / f'model_search_{args.tag}.json').write_text(json.dumps(payload, indent=2, default=float) + '\n', encoding='utf-8', newline='\n')
    md = [f'# Model search `{args.tag}` (end-to-end macro-F0.5; policy tuned on val-A, reported on val-B)', '', f'{len(features)} features; train `{args.train}`, validation `{args.val}` (protocol A corpus). '
          'Selection = best val-A; quote val-B. The holdout was not used.', '', '| variant | val-A | **val-B** | policy (tau, top-k) | singleton FP rate | TP | FP | seconds |', '|---|---:|---:|---|---:|---:|---:|---:|']
    md += [f"| {r['variant']} | {r['val_A']:.4f} | **{r['val_B']:.4f}** | {r['policy']['tau']}, {r['policy']['top_k']} | {100 * r['singleton_fp_rate']:.2f}% | {r['tp']:,} | {r['fp']:,} | {r['seconds']:.0f} |" for r in results]
    md += ['', f"Winner by val-A: **{winner['variant']}**.", '', '## Calibration of the winner', '', '| calibration | val-A | val-B | policy |', '|---|---:|---:|---|']
    md += [f"| {c['calibration']} | {c['val_A']:.4f} | {c['val_B']:.4f} | {c['policy']} |" for c in calib]
    (OUT / f'model_search_{args.tag}.md').write_text('\n'.join(md) + '\n', encoding='utf-8', newline='\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
