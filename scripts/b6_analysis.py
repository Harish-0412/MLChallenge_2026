"""Member B / B6: hard-negative EDA, the sampling specification and the per-stratum error analysis of the first classifier.

    python scripts/b6_analysis.py

Inputs (built by scripts/train_ranker.py): data/benchmarks/pairs_train50k.parquet, pairs_val20k.parquet, queries_*.parquet, data/models_ranker/*.
Outputs: reports/eda/hard_negative_spec.md, reports/eda/b6_analysis.json, reports/eda/error_analysis_val.md
The model is used ONLY to analyse errors; nothing here changes the model, the folds or the policy.
"""
import json
import pickle
import sys
from pathlib import Path

import duckdb
import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from ranking import model as rm  # noqa: E402
from ranking import pairs as rp  # noqa: E402

BENCH = ROOT / 'data' / 'benchmarks'
OUT = ROOT / 'reports' / 'eda'
FLAGS = (ROOT / 'data' / 'scratch' / 'label_pairs.parquet').as_posix()
FEATURES = ROOT / 'data' / 'features' / 'feat_v2_0' / 'split=train'
SALT = 'ranker-v1'


def pct(x):
    return f'{100 * x:.2f}%'


def pair_eda(con) -> dict:
    p = (BENCH / 'pairs_train50k.parquet').as_posix()
    res = {}
    res['strata'] = con.execute(f"""
        SELECT evidence_slice, count(*) AS pairs, sum(is_positive) AS positives, avg(is_positive) AS rate, count(DISTINCT s1_entity_id) AS queries
        FROM read_parquet('{p}') GROUP BY 1 ORDER BY 3 DESC""").fetchall()
    res['by_country'] = con.execute(f"SELECT country, count(*), sum(is_positive), avg(is_positive) FROM read_parquet('{p}') GROUP BY 1 ORDER BY 1").fetchall()
    # what makes a negative "hard": the strongest lexical evidence it carries (similarity ratios are on a 0-1 scale)
    res['negative_kinds'] = con.execute(f"""
        WITH x AS (SELECT is_positive,
              CASE WHEN name_core_ratio >= 0.95 AND address_token_jaccard >= 0.5 THEN 'A same cleaned name AND similar address'
                   WHEN name_core_ratio >= 0.95 THEN 'B same cleaned name, different address'
                   WHEN address_token_jaccard >= 0.8 THEN 'C similar address, different name'
                   WHEN name_core_ratio >= 0.80 AND address_token_jaccard >= 0.3 THEN 'D similar name and partly similar address'
                   WHEN name_core_ratio >= 0.80 OR address_token_jaccard >= 0.5 THEN 'E one moderately similar field'
                   ELSE 'F weak (retrieved by rare token or n-gram only)' END AS kind
              FROM read_parquet('{p}'))
        SELECT kind, count(*) FILTER (WHERE is_positive = 0) AS negatives, count(*) FILTER (WHERE is_positive = 1) AS positives,
               avg(is_positive) AS positive_rate FROM x GROUP BY 1 ORDER BY 1""").fetchall()
    res['per_query'] = con.execute(f"""
        WITH q AS (SELECT s1_entity_id, count(*) n, sum(is_positive) pos FROM read_parquet('{p}') GROUP BY 1)
        SELECT avg(n), quantile_cont(n, 0.5), quantile_cont(n, 0.99), max(n), avg(pos), avg((pos = 0)::INT) FROM q""").fetchone()
    res['by_rank'] = con.execute(f"""
        SELECT CASE WHEN best_sparse_rank <= 3 THEN '1-3' WHEN best_sparse_rank <= 10 THEN '4-10' WHEN best_sparse_rank <= 20 THEN '11-20' ELSE 'none/21+' END AS bucket,
               count(*), avg(is_positive) FROM read_parquet('{p}') GROUP BY 1 ORDER BY 1""").fetchall()
    return res


def score_val(features):
    from xgboost import XGBClassifier
    model = XGBClassifier()
    model.load_model(str(ROOT / 'data' / 'models_ranker' / 'xgb_ranker_v1.json'))
    iso = pickle.loads((ROOT / 'data' / 'models_ranker' / 'isotonic_v1.pkl').read_bytes())
    table = pq.read_table(BENCH / 'pairs_val20k.parquet')
    X = np.column_stack([table.column(f).to_numpy(zero_copy_only=False) for f in rp.assert_model_features(features)]).astype(np.float32)
    prob = iso.predict(model.predict_proba(X)[:, 1])
    del X
    return table, prob


def error_analysis(con, results: dict) -> dict:
    table, prob = score_val(rp.MODEL_FEATURES)
    ids = np.array(table.column('s1_entity_id').to_numpy(zero_copy_only=False))
    tgt = np.array(table.column('candidate_entity_id').to_numpy(zero_copy_only=False))
    y = table.column('is_positive').to_numpy(zero_copy_only=False).astype(np.int8)
    stratum = np.array(table.column('evidence_slice').to_numpy(zero_copy_only=False))
    queries = pq.read_table(BENCH / 'queries_val20k.parquet').to_pydict()
    order = np.argsort(np.array(queries['id']))
    qids = np.array(queries['id'])[order]
    n_true = np.array(queries['match_count'], dtype=float)[order]
    country = np.array(queries['country'])[order]
    code = np.searchsorted(qids, ids)
    val_b = np.array([rm.stable_bucket(i, SALT + '-val') >= 50 for i in qids])
    pol = results['threshold_policy']
    keep = val_b[code]
    idx_b = np.flatnonzero(val_b)
    remap = -np.ones(len(qids), dtype=int)
    remap[idx_b] = np.arange(len(idx_b))
    qb, yb, pb, sb, tb, idb = remap[code[keep]], y[keep], prob[keep], stratum[keep], tgt[keep], ids[keep]
    nb, cb = n_true[idx_b], country[idx_b]
    sel = rm.select_threshold(qb, pb, pol['tau'], pol['top_k'], pol['margin'])
    per_q = rm.macro_f05_from_selection(qb, yb, sel, nb, per_query=True)
    total_links = int(nb.sum())
    cand_pos = int(yb.sum())
    tp = int((sel & (yb == 1)).sum())
    fp = int((sel & (yb == 0)).sum())
    out = {'val_B_queries': int(len(nb)), 'val_B_links': total_links, 'links_in_candidates': cand_pos, 'true_positives_selected': tp, 'false_positives': fp,
           'links_missed_by_retrieval': total_links - cand_pos, 'links_retrieved_but_rejected': cand_pos - tp, 'macro_f05': float(per_q.mean())}
    # loss decomposition: how much macro-F0.5 is lost per source of error (queries with F < 1)
    single = nb == 0
    out['loss'] = {'singleton_queries_with_false_positive': float(np.mean(per_q[single] == 0)) if single.any() else 0.0,
                   'mean_loss_singletons': float((1 - per_q[single]).sum() / len(nb)), 'mean_loss_nonsingleton': float((1 - per_q[~single]).sum() / len(nb))}
    rows = []
    for s in sorted(set(sb)):
        m = sb == s
        rows.append({'stratum': s, 'pairs': int(m.sum()), 'positives': int(yb[m].sum()), 'selected': int(sel[m].sum()), 'tp': int((sel & (yb == 1) & m).sum()),
                     'fp': int((sel & (yb == 0) & m).sum()), 'fn_retrieved_rejected': int(((~sel) & (yb == 1) & m).sum())})
    out['by_stratum'] = rows
    # link-level error types of the retrieved-but-rejected links and of the false positives
    con.execute('CREATE TEMP TABLE fn AS SELECT * FROM (VALUES (1)) t(x)')
    fn_mask = (~sel) & (yb == 1)
    fp_mask = sel & (yb == 0)
    con.register('fn_pairs', __import__('pyarrow').table({'q': idb[fn_mask], 't': tb[fn_mask]}))
    out['fn_error_types'] = con.execute(f"SELECT p.error_type, count(*) FROM fn_pairs f JOIN read_parquet('{FLAGS}') p ON p.q = f.q AND p.t = f.t GROUP BY 1 ORDER BY 2 DESC").fetchall()
    con.register('fp_pairs', __import__('pyarrow').table({'q': idb[fp_mask], 't': tb[fp_mask], 'p': pb[fp_mask]}))
    out['fp_by_confidence'] = con.execute("SELECT CASE WHEN p >= 0.9 THEN '0.9-1.0' WHEN p >= 0.7 THEN '0.7-0.9' ELSE '0.5-0.7' END, count(*) FROM fp_pairs GROUP BY 1 ORDER BY 1").fetchall()
    # the same-name-different-record confusion: do the false positives share the query's exact cleaned name?
    out['fp_same_cleaned_name'] = float(np.mean(table.column('name_core_ratio').to_numpy(zero_copy_only=False)[keep][fp_mask] >= 0.95)) if fp_mask.any() else 0.0
    # examples for hand review (raw text)
    def examples(mask, k=12):
        pick = np.flatnonzero(mask)
        pick = pick[np.argsort([hash((idb[i], tb[i])) % 100003 for i in pick])][:k]
        con.register('ex', __import__('pyarrow').table({'q': idb[pick], 't': tb[pick], 'p': pb[pick]}))
        glob = (FEATURES / 'source=*' / 'country=*' / '*.parquet').as_posix()
        return con.execute(f"""SELECT e.q, e.t, round(e.p, 3), a.business_name, a.business_address, b.business_name, b.business_address
                               FROM ex e JOIN read_parquet('{glob}', hive_partitioning=false) a ON a.entity_id = e.q
                                         JOIN read_parquet('{glob}', hive_partitioning=false) b ON b.entity_id = e.t""").fetchall()
    out['fp_examples'] = examples(fp_mask)
    out['fn_examples'] = examples(fn_mask)
    return out


def main() -> int:
    con = duckdb.connect()
    con.execute("SET threads=4; SET memory_limit='6GB'")
    results = json.loads((OUT / 'ranker_v1_results.json').read_text(encoding='utf-8'))
    eda = pair_eda(con)
    err = error_analysis(con, results)
    (OUT / 'b6_analysis.json').write_text(json.dumps({'pair_eda': eda, 'error_analysis': err}, indent=2, default=float) + '\n', encoding='utf-8', newline='\n')
    pq_ = eda['per_query']
    md = ['# B6 - hard negatives: pair EDA, sampling specification and error analysis', '',
          f'Training pairs come from 50,000 dev queries retrieved from the dev-fold corpus (`pairs_train50k.parquet`): {sum(r[1] for r in eda["strata"]):,} candidate pairs, '
          f'{sum(r[2] for r in eda["strata"]):,} true links (positive rate {pct(sum(r[2] for r in eda["strata"]) / sum(r[1] for r in eda["strata"]))}); per query mean {pq_[0]:.1f} candidates '
          f'(p50 {pq_[1]:.0f}, p99 {pq_[2]:.0f}, max {pq_[3]:.0f}) and {pq_[4]:.2f} true links; {pct(pq_[5])} of queries have no true link among their candidates.', '',
          '## Retrieval strata (`evidence_slice`, the way a candidate was found)', '', '| stratum | pairs | true links | positive rate | queries |', '|---|---:|---:|---:|---:|']
    md += [f'| {s} | {n:,} | {p:,} | {pct(r)} | {q:,} |' for s, n, p, r, q in eda['strata']]
    md += ['', '## What makes a negative hard (lexical evidence a negative carries)', '', '| kind | negatives | positives | positive rate |', '|---|---:|---:|---:|']
    md += [f'| {k} | {n:,} | {p:,} | {pct(r)} |' for k, n, p, r in eda['negative_kinds']]
    md += ['', '## Positive rate by the best sparse-channel rank', '', '| best rank | pairs | positive rate |', '|---|---:|---:|'] + [f'| {b} | {n:,} | {pct(r)} |' for b, n, r in eda['by_rank']]
    md += ['', '## Sampling specification (`train_v1`)', '',
           '**What the first classifier used:** every candidate of every training query, in its natural distribution, no subsampling and no sample weights (`sample_weight = 1`). '
           'This keeps the calibration of the probabilities intact, and macro-F0.5 on the held-out queries is 0.9708 (protocol A, small corpus).', '',
           '**Rules that hold for any training set derived from these candidates:**', '',
           '1. Unit of sampling = the query: all candidates of a query stay together, and a query is in exactly one of `fit`, `early-stop`, `calibration` (80/10/10 by hash of the id, salt `ranker-v1`), all inside the dev fold.',
           '2. Positives = every true link that retrieval found. **A true link that retrieval missed is never turned into a negative and never injected** (recall loss stays visible in validation).',
           '3. Negatives = the retrieved non-links (hard by construction: they were found by a name, address, skeleton, n-gram or embedding channel). A random-negative stratum is optional and only for calibration comparisons.',
           '4. If the training set must be shrunk (memory, or the 10x larger dev corpus): keep all positives; keep per query at most 20 negatives, taking them in proportion to the strata above with '
           'all negatives of kinds A, C and D always kept (they are rare, about 53,000 of 15.4M negatives, and are the ones that decide precision), kind B (same cleaned name, different address: 1.09M negatives, positive rate 0.97%) capped at 8 per query, kinds E and F capped at 6 each per query keeping the best-ranked; store the inclusion probability and train with `sample_weight = 1 / probability`. '
           'Calibrate on an UNSAMPLED calibration slice, otherwise the probabilities are biased.',
           '5. Excluded from features: ids, fold, truth cardinality, `match_count`, sampling weights, `evidence_slice`, any label-derived field. The allowlist is enforced by `ranking.pairs.assert_model_features` (tested).',
           '6. Sampling must be a deterministic function of (seed, query id, target id); `modeling.sampling.sample_training_pairs` implements this and is tested. The down-sampled variant above is **specified but not trained**: the natural distribution was small enough to train on directly.', '',
           '## Error analysis of the first classifier on held-out validation queries (val-B)', '',
           f"{err['val_B_queries']:,} queries, {err['val_B_links']:,} true links: {err['links_in_candidates']:,} were retrieved as candidates ({pct(err['links_in_candidates'] / err['val_B_links'])}); "
           f"the policy selected {err['true_positives_selected']:,} of them and {err['false_positives']:,} false matches. **Macro-F0.5 = {err['macro_f05']:.4f}.** "
           f"Missed by retrieval: {err['links_missed_by_retrieval']:,}; retrieved but rejected: {err['links_retrieved_but_rejected']:,}.", '',
           f"Loss decomposition (share of the 1.0 lost, averaged over all queries): singleton queries {err['loss']['mean_loss_singletons']:.4f} "
           f"({pct(err['loss']['singleton_queries_with_false_positive'])} of singletons received a false match), queries with true links {err['loss']['mean_loss_nonsingleton']:.4f}.", '',
           '| stratum | pairs | true links | selected | TP | FP | retrieved but rejected |', '|---|---:|---:|---:|---:|---:|---:|']
    md += [f"| {r['stratum']} | {r['pairs']:,} | {r['positives']:,} | {r['selected']:,} | {r['tp']:,} | {r['fp']:,} | {r['fn_retrieved_rejected']:,} |" for r in err['by_stratum']]
    md += ['', 'Retrieved-but-rejected links by error type of the link:', '', '| error type | links |', '|---|---:|'] + [f'| {e} | {n:,} |' for e, n in err['fn_error_types']]
    md += ['', f"False positives by calibrated probability: {', '.join(f'{b}: {n:,}' for b, n in err['fp_by_confidence'])}. "
           f"Share of false positives whose cleaned name equals the query's ({'name_core_ratio >= 95'}): {pct(err['fp_same_cleaned_name'])}.", '',
           '## Examples for hand review (raw text)', '', '**False positives** (selected but not a true link): query name / address -> selected candidate name / address (probability)', '']
    md += [f"- `{q}` {a!r} | {b!r} -> `{t}` {c!r} | {d!r} ({p})" for q, t, p, a, b, c, d in err['fp_examples']]
    md += ['', '**Retrieved but rejected true links**', '']
    md += [f"- `{q}` {a!r} | {b!r} -> `{t}` {c!r} | {d!r} ({p})" for q, t, p, a, b, c, d in err['fn_examples']]
    (OUT / 'hard_negative_spec.md').write_text('\n'.join(md) + '\n', encoding='utf-8', newline='\n')
    (OUT / 'error_analysis_val.md').write_text('\n'.join(md[md.index('## Error analysis of the first classifier on held-out validation queries (val-B)'):]) + '\n', encoding='utf-8', newline='\n')
    print('\n'.join(md[:12]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
