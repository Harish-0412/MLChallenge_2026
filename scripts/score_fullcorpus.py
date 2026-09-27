"""Protocol B: score the FROZEN classifier and policy (trained on dev, tuned on val-A of protocol A) on validation queries that retrieved from the complete
training target corpus (about 10.3M targets, the size the test faces).

    python scripts/score_fullcorpus.py --name valfull5k

Reports macro-F0.5 on the queries that were NOT used to tune the policy (val-B by the same hash) and on all sampled queries, the retrieval recall/size table on the
full corpus, the oracle, and the loss decomposition. Nothing is refitted.
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
from ranking import pairs as rp  # noqa: E402

OUT = ROOT / 'reports' / 'eda'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    parser.add_argument('--model', default='xgb_ranker_v1')
    parser.add_argument('--emb', action='store_true')
    args = parser.parse_args()
    from xgboost import XGBClassifier
    model = XGBClassifier()
    model.load_model(str(ROOT / 'data' / 'models_ranker' / f'{args.model}.json'))
    iso_name = 'isotonic_v1.pkl' if args.model == 'xgb_ranker_v1' else 'isotonic_v2_emb.pkl'
    iso = pickle.loads((ROOT / 'data' / 'models_ranker' / iso_name).read_bytes())
    results_name = 'ranker_v1_results.json' if args.model == 'xgb_ranker_v1' else 'ranker_v2_emb_results.json'
    frozen = json.loads((OUT / results_name).read_text(encoding='utf-8'))['threshold_policy']
    if args.emb:
        __import__('subprocess').run(['C:/SideQuest/ML Challenge/.venv/Scripts/python.exe', 'scripts/merge_emb.py', '--name', args.name], check=True, cwd=str(ROOT))
        args.name = args.name + 'E'
    tr.ensure_pairs(args.name, False)
    features = rp.MODEL_FEATURES_E if args.emb else rp.MODEL_FEATURES
    D = tr.load(args.name, features)
    prob = iso.predict(model.predict_proba(D['X'])[:, 1])
    is_b = np.array([rm.stable_bucket(i, tr.SALT + '-val') >= 50 for i in D['ids']])
    result = {'name': args.name, 'queries': int(len(D['ids'])), 'pairs': int(len(D['y'])), 'frozen_policy': {k: frozen[k] for k in ('tau', 'top_k', 'margin')}}
    for label, mask_q in (('val-B queries (not used to tune the policy)', is_b), ('all sampled queries', np.ones(len(D['ids']), bool))):
        idx = np.flatnonzero(mask_q)
        remap = -np.ones(len(mask_q), dtype=int)
        remap[idx] = np.arange(len(idx))
        rows = mask_q[D['code']]
        q, y, p, n = remap[D['code'][rows]], D['y'][rows], prob[rows], D['n_true'][idx]
        sel = rm.select_threshold(q, p, frozen['tau'], frozen['top_k'], frozen['margin'])
        per_q = rm.macro_f05_from_selection(q, y, sel, n, per_query=True)
        single = n == 0
        cnt = np.bincount(q, minlength=len(n))
        result[label] = {
            'queries': int(len(idx)), 'macro_f05': float(per_q.mean()), 'oracle_macro_f05': rm.macro_f05_from_selection(q, y, y == 1, n),
            'all_empty': rm.macro_f05_from_selection(q, y, np.zeros(len(y), bool), n), 'links': int(n.sum()), 'links_in_candidates': int(y.sum()),
            'recall': float(y.sum() / n.sum()), 'zero_candidate_rate': float(np.mean(cnt == 0)), 'candidates_mean': float(cnt.mean()), 'candidates_p99': float(np.quantile(cnt, 0.99)),
            'tp': int((sel & (y == 1)).sum()), 'fp': int((sel & (y == 0)).sum()), 'singleton_false_positive_rate': float(np.mean(per_q[single] == 0)) if single.any() else float('nan'),
            'by_country': {c: float(per_q[D['country'][idx] == c].mean()) for c in ('India', 'US')}}
    # ---- policy tuned where the density matches the test: (ii) on the protocol-B val-A queries, (iii) on the dev calibration queries (dev corpus is ~8M targets)
    taus, topks = np.round(np.arange(0.05, 0.96, 0.05), 2), (1, 2, 3, 5, 8, 12)

    def split_arrays(mask_q):
        idx = np.flatnonzero(mask_q)
        remap = -np.ones(len(mask_q), dtype=int)
        remap[idx] = np.arange(len(idx))
        rows = mask_q[D['code']]
        return remap[D['code'][rows]], D['y'][rows], prob[rows], D['n_true'][idx]
    qa_, ya_, pa_, na_ = split_arrays(~is_b)
    qb_, yb_, pb_, nb_ = split_arrays(is_b)
    pol_ii, score_ii = rm.search_threshold_policy(qa_, pa_, ya_, na_, taus, topks)
    res = {'(i) frozen from protocol A (small corpus)': dict(frozen)}
    Dt = tr.load('train50kE' if args.emb else 'train50k', features)
    prob_t = iso.predict(model.predict_proba(Dt['X'])[:, 1])
    role_t = np.array([rm.stable_bucket(i, tr.SALT) for i in Dt['ids']])
    cal_q = role_t >= 90
    idx = np.flatnonzero(cal_q)
    remap = -np.ones(len(cal_q), dtype=int)
    remap[idx] = np.arange(len(idx))
    rows = cal_q[Dt['code']]
    pol_iii, score_iii = rm.search_threshold_policy(remap[Dt['code'][rows]], prob_t[rows], Dt['y'][rows], Dt['n_true'][idx], taus, topks)
    del Dt
    variants = {}
    for label, pol in (('(i) frozen policy tuned on the small validation corpus', frozen), ('(ii) tuned on protocol-B val-A queries', pol_ii), ('(iii) tuned on the dev calibration queries (dev corpus, matched density)', pol_iii)):
        sel = rm.select_threshold(qb_, pb_, pol['tau'], pol['top_k'], pol.get('margin', 0.0))
        per_q = rm.macro_f05_from_selection(qb_, yb_, sel, nb_, per_query=True)
        variants[label] = {'policy': {k: pol[k] for k in ('tau', 'top_k')}, 'val_B_macro_f05': float(per_q.mean()), 'tp': int((sel & (yb_ == 1)).sum()), 'fp': int((sel & (yb_ == 0)).sum()),
                           'singleton_fp_rate': float(np.mean(per_q[nb_ == 0] == 0))}
    result['policy_variants_val_B'] = variants
    (OUT / f'fullcorpus_{args.name}.json').write_text(json.dumps(result, indent=2, default=float) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result['policy_variants_val_B'], indent=2, default=float))
    return 0


if __name__ == '__main__':
    sys.exit(main())
