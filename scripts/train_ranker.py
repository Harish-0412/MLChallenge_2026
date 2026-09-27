"""Member B: train the pair classifier on dev-fold candidates, calibrate, tune the decision policy on part of the validation queries and report the
macro-F0.5 on the other part of the validation queries (the locked holdout is never touched).

    python scripts/train_ranker.py --train train50k --val val20k [--rebuild-pairs]

Data flow: candidates (features only) -> labeled pair tables (B6, labels attached here) -> XGBoost on `fit` queries (dev), early stopping on `es`
queries (dev), isotonic calibration on `cal` queries (dev) -> scores on validation queries -> policy tuned on val-A, reported on val-B.
Protocol note: validation candidates come from the val-fold corpus (1.03M targets, protocol A), which is easier than the 10M-target test corpus.
"""
import argparse
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
from validation import scorer  # noqa: E402

BENCH = ROOT / 'data' / 'benchmarks'
FLAGS = (ROOT / 'data' / 'scratch' / 'label_pairs.parquet').as_posix()
FEATURE_ROOT = ROOT / 'data' / 'features' / 'feat_v2_0' / 'split=train'
OUT = ROOT / 'reports' / 'eda'
MODELS = ROOT / 'data' / 'models_ranker'
SALT = 'ranker-v1'
GROUPS = {
    'name': ['name_key_equal', 'name_hyg_ratio', 'name_hyg_token_set_ratio', 'name_core_ratio', 'name_core_token_jaccard', 'name_core_char3_dice', 'name_core_compact_equal',
             'name_accent_ratio', 'name_translit_ratio', 'name_skeleton_ratio', 'legal_form_equal', 'legal_form_both_present', 'name_informative_min', 'name_same_script',
             'name_cross_script', 'name_placeholder_any', 'name_domain_any'],
}
GROUPS['address'] = ['address_missing_any', 'address_missing_both', 'address_canon_ratio', 'address_token_jaccard', 'address_char3_dice', 'address_segment_jaccard', 'address_state_equal',
                     'address_state_both_present', 'address_state_conflict_any', 'address_city_overlap', 'address_postal_overlap', 'address_number_jaccard', 'address_number_shared',
                     'address_number_conflicts', 'address_number_context_jaccard', 'address_parse_conf_min']
GROUPS['retrieval'] = ['retrieval_channel_count', 'retrieval_score_max', 'retrieval_rank_best', 'candidate_block_size', 'query_candidate_count'] + rp.EXTRA_FEATURES + rp.EMB_FEATURES


def ensure_pairs(name: str, rebuild: bool) -> Path:
    out = BENCH / f'pairs_{name}.parquet'
    if out.exists() and not rebuild:
        return out
    t0 = time.perf_counter()
    cand_v1 = BENCH / f'_candv1_{name}.parquet'
    info = rp.aggregate_candidates((BENCH / f'cand_{name}.parquet').as_posix(), (BENCH / f'queries_{name}.parquet').as_posix(), cand_v1.as_posix(), FLAGS)
    print(f'[{name}] candidate_v1 table: {info}', flush=True)
    if out.exists():
        out.unlink()
    res = rp.build_pairs((BENCH / f'cand_{name}.parquet').as_posix(), cand_v1.as_posix(), FEATURE_ROOT.as_posix(), out.as_posix(), (BENCH / f'_work_{name}').as_posix(), with_emb=name.endswith('E'))
    cand_v1.unlink()
    print(f'[{name}] pair features: {res} in {time.perf_counter() - t0:.0f}s', flush=True)
    return out


def load(name: str, features):
    path = ensure_pairs(name, False)
    table = pq.read_table(path)
    q_ids = table.column('s1_entity_id').to_numpy(zero_copy_only=False)
    queries = pq.read_table(BENCH / f'queries_{name}.parquet').to_pydict()
    order = np.argsort(np.array(queries['id']))
    ids = np.array(queries['id'])[order]
    n_true = np.array(queries['match_count'], dtype=float)[order]
    country = np.array(queries['country'])[order]
    code = np.searchsorted(ids, q_ids)
    assert (ids[code] == q_ids).all(), 'a pair belongs to an unknown query'
    X = np.column_stack([table.column(f).to_numpy(zero_copy_only=False) for f in rp.assert_model_features(features)]).astype(np.float32)
    y = table.column('is_positive').to_numpy(zero_copy_only=False).astype(np.int8)
    assert set(np.unique(y)) <= {0, 1}
    return {'ids': ids, 'n_true': n_true, 'country': country, 'code': code, 'X': X, 'y': y, 'stratum': table.column('evidence_slice').to_numpy(zero_copy_only=False),
            'target': table.column('candidate_entity_id').to_numpy(zero_copy_only=False)}


def query_flags(ids):
    con = duckdb.connect()
    con.execute('CREATE TABLE q(id VARCHAR)')
    con.executemany('INSERT INTO q VALUES (?)', [(i,) for i in ids])
    rows = con.execute(f"""SELECT q.id, coalesce(f.c, false), coalesce(f.m, false), coalesce(f.n, false) FROM q LEFT JOIN
        (SELECT q AS id, bool_or(cross_script) c, bool_or(tgt_addr_missing) m, bool_or(number_conflict) n FROM read_parquet('{FLAGS}') GROUP BY q) f USING (id) ORDER BY q.id""").fetchall()
    return {'cross_script': np.array([r[1] for r in rows]), 'target_address_missing': np.array([r[2] for r in rows]), 'number_conflict': np.array([r[3] for r in rows])}


def report_slices(D, sel, mask_q, label):
    """Macro-F0.5 restricted to the queries in ``mask_q`` (all queries of the slice count)."""
    idx = np.flatnonzero(mask_q)
    remap = -np.ones(len(mask_q), dtype=int)
    remap[idx] = np.arange(len(idx))
    keep = mask_q[D['code']]
    f = rm.macro_f05_from_selection(remap[D['code'][keep]], D['y'][keep], sel[keep], D['n_true'][idx])
    return {'slice': label, 'queries': int(len(idx)), 'macro_f05': f}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--train', default='train50k')
    parser.add_argument('--val', default='val20k')
    parser.add_argument('--rebuild-pairs', action='store_true')
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--no-ablations', action='store_true')
    parser.add_argument('--emb', action='store_true', help='use the embedding-channel candidate sets <name>E and the 76-feature variant')
    args = parser.parse_args()
    started = time.perf_counter()
    if args.emb:
        args.train, args.val = args.train + 'E', args.val + 'E'
    for name in (args.val, args.train):
        ensure_pairs(name, args.rebuild_pairs)
    features = rp.MODEL_FEATURES_E if args.emb else rp.MODEL_FEATURES
    train, val = load(args.train, features), load(args.val, features)
    print(f'train pairs {len(train["y"]):,} ({int(train["y"].sum()):,} positive) over {len(train["ids"]):,} queries; val pairs {len(val["y"]):,} over {len(val["ids"]):,} queries', flush=True)

    # ---- disjoint query groups: dev fit / early-stop / calibration; validation tune (A) / report (B)
    bucket = np.array([rm.stable_bucket(i, SALT) for i in train['ids']])
    role = np.where(bucket < 80, 0, np.where(bucket < 90, 1, 2))           # 0 fit, 1 early stop, 2 calibration
    vb = np.array([rm.stable_bucket(i, SALT + '-val') for i in val['ids']])
    val_a = vb < 50
    row_role = role[train['code']]
    fit, es, cal = row_role == 0, row_role == 1, row_role == 2
    assert not (set(train['ids'][role == 0]) & set(train['ids'][role == 2]))

    def fit_and_score(cols, tag):
        idx = [features.index(c) for c in cols]
        m = rm.fit_xgb(train['X'][fit][:, idx], train['y'][fit], train['X'][es][:, idx], train['y'][es], device=args.device)
        iso = rm.fit_isotonic(m.predict_proba(train['X'][cal][:, idx])[:, 1], train['y'][cal])
        raw = m.predict_proba(val['X'][:, idx])[:, 1]
        print(f'  [{tag}] {len(cols)} features, {m.best_iteration + 1 if hasattr(m, "best_iteration") else "?"} trees', flush=True)
        return m, iso, raw, iso.predict(raw)

    model, iso, raw, prob = fit_and_score(features, 'full')
    from sklearn.metrics import average_precision_score, log_loss, roc_auc_score
    diag = {'auc': float(roc_auc_score(val['y'], raw)), 'average_precision': float(average_precision_score(val['y'], raw)),
            'logloss_calibrated': float(log_loss(val['y'], np.clip(prob, 1e-6, 1 - 1e-6)))}
    print('diagnostics (never used for selection):', diag, flush=True)

    # ---- policies: tune on val-A, report on val-B
    A_rows, B_rows = val_a[val['code']], ~val_a[val['code']]

    def sub(mask_rows, mask_q):
        idx = np.flatnonzero(mask_q)
        remap = -np.ones(len(mask_q), dtype=int)
        remap[idx] = np.arange(len(idx))
        return remap[val['code'][mask_rows]], val['y'][mask_rows], val['n_true'][idx]
    qa, ya, na = sub(A_rows, val_a)
    qb, yb, nb = sub(B_rows, ~val_a)
    pa_, pb_ = prob[A_rows], prob[B_rows]
    taus = np.round(np.arange(0.05, 0.96, 0.05), 2)
    best_thr, score_a = rm.search_threshold_policy(qa, pa_, ya, na, taus, (1, 2, 3, 5, 8, 12), (0.0, 0.1, 0.2))
    recall_est = float((val['y'][A_rows].sum()) / max(na.sum(), 1))
    best_exp, score_a_exp = None, -1.0
    for tk in (5, 8, 12):
        for bias in (0.0, 0.02, 0.05, 0.1):
            s = rm.macro_f05_from_selection(qa, ya, rm.select_expected_f(qa, pa_, recall_est, tk, bias), na)
            if s > score_a_exp:
                best_exp, score_a_exp = {'top_k': tk, 'empty_bias': bias, 'recall_est': recall_est}, s
    sel_thr_b = rm.select_threshold(qb, pb_, best_thr['tau'], best_thr['top_k'], best_thr['margin'])
    sel_exp_b = rm.select_expected_f(qb, pb_, best_exp['recall_est'], best_exp['top_k'], best_exp['empty_bias'])
    f_thr = rm.macro_f05_from_selection(qb, yb, sel_thr_b, nb)
    f_exp = rm.macro_f05_from_selection(qb, yb, sel_exp_b, nb)
    oracle = rm.macro_f05_from_selection(qb, yb, yb == 1, nb)
    all_empty = rm.macro_f05_from_selection(qb, yb, np.zeros(len(yb), bool), nb)
    print(f'val-B macro-F0.5: threshold policy {f_thr:.4f} {best_thr}; expected-F policy {f_exp:.4f} {best_exp}; oracle {oracle:.4f}; all-empty {all_empty:.4f}', flush=True)
    chosen_name, chosen_sel = ('expected_f', sel_exp_b) if f_exp >= f_thr else ('threshold', sel_thr_b)

    # ---- cross-check the vectorised evaluator against the independent set-based scorer on val-B
    ids_b = val['ids'][~val_a]
    tgt_b = val['target'][B_rows]
    truth_con = duckdb.connect()
    tr = truth_con.execute(f"SELECT q, list(t) FROM read_parquet('{FLAGS}') WHERE q IN (SELECT unnest(?)) GROUP BY q", [list(ids_b)]).fetchall()
    truth = {q: ts for q, ts in tr}
    qcodes_b = qb
    preds = {q: [] for q in ids_b}
    for row in np.flatnonzero(chosen_sel):
        preds[ids_b[qcodes_b[row]]].append(tgt_b[row])
    ref = scorer.macro_f05_sets({q: truth.get(q, []) for q in ids_b}, preds)['macro_f05']
    fast = f_exp if chosen_name == 'expected_f' else f_thr
    assert abs(ref - fast) < 1e-9, (ref, fast)
    print(f'evaluator cross-check vs validation.scorer: {ref:.10f} == {fast:.10f}', flush=True)

    # ---- slices on val-B
    flags = query_flags(val['ids'])
    idx_b = np.flatnonzero(~val_a)
    country_b = val['country'][idx_b]
    slices = []
    Db = {'code': qb, 'y': yb, 'n_true': nb}
    full_mask = np.ones(len(idx_b), dtype=bool)
    defs = [('all val-B queries', full_mask), ('India', country_b == 'India'), ('US', country_b == 'US'), ('singleton queries (0 true links)', nb == 0),
            ('match count 1', nb == 1), ('match count 2', nb == 2), ('match count 3-4', (nb >= 3) & (nb <= 4)), ('match count 5+', nb >= 5),
            ('has a cross-script target', flags['cross_script'][idx_b]), ('has a target with missing address', flags['target_address_missing'][idx_b]),
            ('has a target with a conflicting number', flags['number_conflict'][idx_b])]
    for label, mask in defs:
        slices.append(report_slices(Db, chosen_sel, mask, label))
    n_single = int((nb == 0).sum())
    single_fp = float(np.mean([bool(np.any(chosen_sel[qb == i])) for i in np.flatnonzero(nb == 0)])) if n_single else float('nan')
    sel_per_q = np.bincount(qb[chosen_sel], minlength=len(nb))
    tp_per_q = np.bincount(qb[chosen_sel & (yb == 1)], minlength=len(nb))

    # ---- ablations by feature group (same protocol; policy re-tuned on val-A each time)
    ablations = []
    for tag, cols in ([] if args.no_ablations else (('base features only (no retrieval provenance)', [c for c in features if c not in GROUPS['retrieval']]),
                      ('name features + retrieval', GROUPS['name'] + GROUPS['retrieval']),
                      ('address features + retrieval', GROUPS['address'] + GROUPS['retrieval']))):
        _m, _iso, _raw, p = fit_and_score(cols, tag)
        best, _s = rm.search_threshold_policy(qa, p[A_rows], ya, na, taus, (1, 2, 3, 5, 8, 12))
        ablations.append({'features': tag, 'n_features': len(cols), 'val_B_macro_f05': rm.macro_f05_from_selection(qb, yb, rm.select_threshold(qb, p[B_rows], best['tau'], best['top_k']), nb),
                          'policy': best})
    importances = sorted(zip(features, model.feature_importances_), key=lambda x: -x[1])[:20]

    MODELS.mkdir(parents=True, exist_ok=True)
    tag = 'v2_emb' if args.emb else 'v1'
    model.save_model(str(MODELS / f'xgb_ranker_{tag}.json'))
    (MODELS / f'isotonic_{tag}.pkl').write_bytes(pickle.dumps(iso))
    result = {'train': args.train, 'val': args.val, 'train_pairs': int(len(train['y'])), 'train_positives': int(train['y'].sum()), 'train_queries': int(len(train['ids'])),
              'val_pairs': int(len(val['y'])), 'val_queries': int(len(val['ids'])), 'val_A_queries': int(val_a.sum()), 'val_B_queries': int((~val_a).sum()),
              'diagnostics': diag, 'threshold_policy': {**best_thr, 'val_A': score_a, 'val_B': f_thr}, 'expected_f_policy': {**best_exp, 'val_A': score_a_exp, 'val_B': f_exp},
              'chosen': chosen_name, 'oracle_val_B': oracle, 'all_empty_val_B': all_empty, 'slices': slices, 'singleton_false_positive_rate': single_fp,
              'mean_selected_per_query': float(sel_per_q.mean()), 'mean_true_positives_per_query': float(tp_per_q.mean()), 'ablations': ablations,
              'top_features': [(n, float(v)) for n, v in importances], 'seconds': time.perf_counter() - started}
    (OUT / f'ranker_{tag}_results.json').write_text(json.dumps(result, indent=2, default=float) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: result[k] for k in ('chosen', 'oracle_val_B', 'all_empty_val_B', 'singleton_false_positive_rate')}, default=float), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
