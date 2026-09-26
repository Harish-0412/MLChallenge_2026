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
    args = parser.parse_args()
    from xgboost import XGBClassifier
    model = XGBClassifier()
    model.load_model(str(ROOT / 'data' / 'models_ranker' / 'xgb_ranker_v1.json'))
    iso = pickle.loads((ROOT / 'data' / 'models_ranker' / 'isotonic_v1.pkl').read_bytes())
    frozen = json.loads((OUT / 'ranker_v1_results.json').read_text(encoding='utf-8'))['threshold_policy']
    tr.ensure_pairs(args.name, False)
    D = tr.load(args.name, rp.MODEL_FEATURES)
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
    (OUT / f'fullcorpus_{args.name}.json').write_text(json.dumps(result, indent=2, default=float) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result, indent=2, default=float))
    return 0


if __name__ == '__main__':
    sys.exit(main())
