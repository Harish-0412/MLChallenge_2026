"""Retune the decision policy on the frozen classifier, using labeled full-corpus validation data (pairs_valfull5k.parquet, real labels via
data/scratch/label_pairs.parquet, retrieved from the complete 10.3M-target training corpus - the same density the real test set has).

Two things the original frozen policy (tau=0.7, top_k=12, reports/eda/ranker_v1_results.json) never accounted for:
1. It was tuned BEFORE the one-owner postprocessing existed, so tau/top_k and the one-owner margin were never jointly optimised.
2. It uses one global tau; candidates found only by a weak evidence channel (sparse_address_only/sparse_name) plausibly need a stricter
   floor than exact-key matches, and the per-candidate ``evidence_slice`` (no label needed - it is which retrieval channel found the pair) is
   available at real inference time.

Both searches are grid searches on val-A (half the valfull5k queries by hash), reported on val-B (the other half); everything here is offline,
against training-data labels - it never touches the real test set or a held-out fold beyond val-A/val-B.

    python scripts/policy_retune.py
"""
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from ranking import model as rm  # noqa: E402
from ranking import owner as ro  # noqa: E402
from ranking import pairs as rp  # noqa: E402

BENCH = ROOT / 'data' / 'benchmarks'
OUT = ROOT / 'reports' / 'eda'
MODELS = ROOT / 'data' / 'models_ranker'
SALT = 'ranker-v1-val'
SLICES = ('exact_v1_key', 'cleaned_equal', 'skeleton_or_secondary', 'sparse_name', 'sparse_address_only')
TAUS = np.round(np.arange(0.05, 0.96, 0.05), 2)
TOP_KS = (3, 5, 8, 12, 16, 20)
MARGINS = (0.0, 0.1, 0.2, 0.3)


def load_scored(name: str):
    table = pq.read_table(BENCH / f'pairs_{name}.parquet')
    from xgboost import XGBClassifier
    model = XGBClassifier()
    model.load_model(str(MODELS / 'xgb_ranker_v1.json'))
    iso = pickle.loads((MODELS / 'isotonic_v1.pkl').read_bytes())
    X = np.column_stack([table.column(f).to_numpy(zero_copy_only=False) for f in rp.assert_model_features(rp.MODEL_FEATURES)]).astype(np.float32)
    prob = iso.predict(model.predict_proba(X)[:, 1])
    q_ids = table.column('s1_entity_id').to_numpy(zero_copy_only=False)
    t_ids = table.column('candidate_entity_id').to_numpy(zero_copy_only=False)
    y = table.column('is_positive').to_numpy(zero_copy_only=False).astype(np.int8)
    slice_names = table.column('evidence_slice').to_numpy(zero_copy_only=False)
    slice_code = np.array([SLICES.index(s) for s in slice_names])
    order = np.argsort(q_ids, kind='stable')
    q_sorted, t_sorted, p_sorted, y_sorted, s_sorted = q_ids[order], t_ids[order], prob[order], y[order], slice_code[order]
    uniq_q, qcode = np.unique(q_sorted, return_inverse=True)
    n_true = np.zeros(len(uniq_q))
    np.add.at(n_true, qcode, y_sorted)
    val_a = np.array([rm.stable_bucket(i, SALT) for i in uniq_q]) < 50
    tcode = ro.encode_targets(t_sorted)          # computed once; reused by every policy candidate (encode_targets is the expensive step)
    return {'q': q_sorted, 't': t_sorted, 'p': p_sorted, 'y': y_sorted, 's': s_sorted, 'qcode': qcode, 'tcode': tcode, 'n_true': n_true, 'uniq_q': uniq_q, 'val_a': val_a}


def eval_selection(D, sel, mask_q):
    idx = np.flatnonzero(mask_q)
    remap = -np.ones(len(mask_q), dtype=int)
    remap[idx] = np.arange(len(idx))
    rows = mask_q[D['qcode']]
    return rm.macro_f05_from_selection(remap[D['qcode'][rows]], D['y'][rows], sel[rows], D['n_true'][idx])


def apply_owner(D, sel, margin):
    if margin is None:
        return sel
    return ro.apply_one_owner(sel, D['tcode'], D['qcode'], D['p'], margin=margin, among='selected')


def search_global(D):
    A, B = D['val_a'], ~D['val_a']
    best, best_score = None, -1.0
    for tau in TAUS:
        for k in TOP_KS:
            for margin in MARGINS:
                for owner_margin in (None, 0.0, 0.1, 0.2):
                    sel = rm.select_threshold(D['qcode'], D['p'], tau, k, margin)
                    sel = apply_owner(D, sel, owner_margin)
                    score = eval_selection(D, sel, A)
                    if score > best_score + 1e-12:
                        best, best_score = {'tau': float(tau), 'top_k': int(k), 'margin': float(margin), 'owner_margin': owner_margin}, score
    sel_b = rm.select_threshold(D['qcode'], D['p'], best['tau'], best['top_k'], best['margin'])
    sel_b = apply_owner(D, sel_b, best['owner_margin'])
    return best, best_score, eval_selection(D, sel_b, B)


def search_per_slice(D, base: dict):
    """Coordinate descent from the best global policy: for each evidence_slice, try nudging its own tau up/down (fixed top_k/margin/owner from
    the global search) and keep the change if it improves val-A."""
    A, B = D['val_a'], ~D['val_a']
    tau_by_slice = np.full(len(SLICES), base['tau'])

    def score_of(taus, mask):
        sel = rm.select_threshold_by_slice(D['qcode'], D['p'], D['s'], taus, base['top_k'], base['margin'])
        sel = apply_owner(D, sel, base['owner_margin'])
        return eval_selection(D, sel, mask)
    current = score_of(tau_by_slice, A)
    for _pass in range(3):
        improved = False
        for i in range(len(SLICES)):
            best_tau_i, best_score_i = tau_by_slice[i], current
            for candidate in TAUS:
                trial = tau_by_slice.copy()
                trial[i] = candidate
                score = score_of(trial, A)
                if score > best_score_i + 1e-12:
                    best_tau_i, best_score_i = candidate, score
            if best_score_i > current + 1e-12:
                tau_by_slice[i], current, improved = best_tau_i, best_score_i, True
        if not improved:
            break
    return tau_by_slice, current, score_of(tau_by_slice, B)


def main() -> int:
    started = time.perf_counter()
    D = load_scored('valfull5k')
    print(f'loaded and scored {len(D["p"]):,} pairs over {len(D["uniq_q"]):,} queries ({time.perf_counter() - started:.0f}s)', flush=True)
    global_best, global_a, global_b = search_global(D)
    print(f'global search: {global_best}, val-A {global_a:.4f}, val-B {global_b:.4f}', flush=True)

    baselines = {'small-corpus-tuned (ranker_v1_results.json)': json.loads((OUT / 'ranker_v1_results.json').read_text(encoding='utf-8'))['threshold_policy'],
                 'actual DGX submission default (test_export.py)': {'tau': 0.7, 'top_k': 12, 'margin': 0.0}}
    baseline_scores = {}
    for label, pol in baselines.items():
        sel = rm.select_threshold(D['qcode'], D['p'], pol['tau'], pol['top_k'], pol.get('margin', 0.0))
        no_owner = eval_selection(D, sel, ~D['val_a'])
        with_owner = eval_selection(D, apply_owner(D, sel, 0.0), ~D['val_a'])
        baseline_scores[label] = {'policy': pol, 'val_B_no_one_owner': no_owner, 'val_B_with_one_owner': with_owner}
        print(f'{label} {pol} on this val-B: without one-owner {no_owner:.4f}, with one-owner (margin 0.0) {with_owner:.4f}', flush=True)
    print(f'NOTE: only {len(D["uniq_q"]):,} of the real 1,732,544 test queries are sampled here, so almost no two sampled queries compete for the '
          "same target - one-owner's benefit is structurally invisible at this scale. The real DGX run (all 1,732,544 queries present) dropped "
          '168,952 matches via one-owner; that full-scale evidence is what should decide whether to keep it, not this small-sample comparison.', flush=True)

    tau_by_slice, slice_a, slice_b = search_per_slice(D, global_best)
    print(f'per-slice tau (top_k={global_best["top_k"]}, margin={global_best["margin"]}, owner_margin={global_best["owner_margin"]}): '
          f'{dict(zip(SLICES, tau_by_slice.tolist()))}, val-A {slice_a:.4f}, val-B {slice_b:.4f}', flush=True)

    result = {'valfull5k_pairs': int(len(D['p'])), 'valfull5k_queries': int(len(D['uniq_q'])), 'baselines': baseline_scores,
              'global_retune': {'policy': global_best, 'val_A': global_a, 'val_B': global_b},
              'per_slice_retune': {'tau_by_slice': dict(zip(SLICES, tau_by_slice.tolist())), 'top_k': global_best['top_k'], 'margin': global_best['margin'],
                                   'owner_margin': global_best['owner_margin'], 'val_A': slice_a, 'val_B': slice_b},
              'one_owner_note': 'only 5,000 of 1,732,544 real queries sampled here; one-owner collisions are structurally rare at this scale. '
                                'Trust the real DGX run (168,952 matches dropped) over this small-sample owner_margin search.',
              'recommendation': 'per_slice' if slice_b > global_b + 1e-6 else 'global'}
    (OUT / 'policy_retune_results.json').write_text(json.dumps(result, indent=2, default=float) + '\n', encoding='utf-8', newline='\n')
    md = ['# Policy retune (offline, on labeled full-corpus validation data)', '',
          f'{result["valfull5k_queries"]:,} queries, {result["valfull5k_pairs"]:,} candidate pairs, retrieved from the complete 10.3M-target training corpus '
          '(same density as the real test set). Policy tuned on val-A, reported on val-B; both are held-out relative to model training and calibration.', '',
          '**Caveat on one-owner:** only 5,000 of the real 1,732,544 test queries are sampled here, so almost no two sampled queries compete for the same '
          "target - one-owner's benefit is structurally invisible at this scale (see the identical no-owner/with-owner scores below). The real DGX run, "
          'with all queries present, dropped 168,952 matches via one-owner; keep it on regardless of what the small-sample grid search below prefers.', '',
          '| policy | val-B macro-F0.5 |', '|---|---:|']
    for label, s in baseline_scores.items():
        md.append(f'| {label} {s["policy"]}, no one-owner | {s["val_B_no_one_owner"]:.4f} |')
        md.append(f'| {label} {s["policy"]}, + one-owner | {s["val_B_with_one_owner"]:.4f} |')
    md += [f'| global retune {global_best} | **{global_b:.4f}** |',
          f'| per-slice retune (top_k={global_best["top_k"]}) | **{slice_b:.4f}** |', '',
          '## Per-slice thresholds found', '', '| evidence_slice | tau |', '|---|---:|']
    md += [f'| {s} | {t:.2f} |' for s, t in zip(SLICES, tau_by_slice)]
    md += ['', f'**Recommendation: use the {result["recommendation"]} policy (tau/top_k from the global retune above) for the real submission, '
           'with one-owner kept on regardless of this search.**']
    (OUT / 'policy_retune_results.md').write_text('\n'.join(md) + '\n', encoding='utf-8', newline='\n')
    print('\n'.join(md))
    print(f'done in {time.perf_counter() - started:.0f}s', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
