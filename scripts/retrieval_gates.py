"""Member B / B5: candidate quality gates on a held-out query set (labels enter only here).

    python scripts/retrieval_gates.py --name val20k

Reads data/benchmarks/queries_<name>.parquet and cand_<name>.parquet (built by build_candidate_set.py), attaches the training labels and reports, for the
final union and for the exact-key baseline: micro link recall, macro recall over non-singletons, all-true-links coverage, zero-candidate rate, oracle
macro-F0.5, candidate-size quantiles, and the same for India/US, match-count buckets, cross-script, missing-address and number-conflict queries, plus a
recall-versus-size curve over k. Verdicts compare against the plan's gates (micro recall >= 99%, oracle >= 0.97).
"""
import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from retrieval import MAX_K, engine, evaluate  # noqa: E402

BENCH = ROOT / 'data' / 'benchmarks'
FLAGS = (ROOT / 'data' / 'scratch' / 'label_pairs.parquet').as_posix()
OUT = ROOT / 'reports' / 'eda'
EQ = [c['name'] for c in engine.EQUALITY_CHANNELS]
SPARSE = [c['name'] for c in engine.POSTINGS_CHANNELS]
ADD_ORDER = ['eq_name_core', 'eq_address_tokset', 'eq_name_compact', 'eq_name_skeleton', 'eq_core_postal', 'eq_core_number', 'eq_skeleton_number',
             'tok_name', 'tri_name', 'tok_address', 'bigram_address']
BASELINE = ['eq_name_key', 'eq_address_key']


def union_spec(sparse_k: int) -> dict:
    spec = {c: MAX_K for c in BASELINE}
    for ch in ADD_ORDER:
        spec[ch] = MAX_K if ch in EQ else sparse_k
    return spec


def pct(x):
    return 'n/a' if x != x else f'{100 * x:.2f}%'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--name', required=True)
    args = parser.parse_args()
    con = duckdb.connect()
    con.execute("SET threads=8; SET memory_limit='10GB'")
    con.execute(f"CREATE TABLE cand AS SELECT channel, q, t, rnk, score FROM read_parquet('{(BENCH / f'cand_{args.name}.parquet').as_posix()}')")
    con.execute(f"""CREATE TABLE bench_q AS
        SELECT b.id, b.country, b.stratum, b.match_count,
               coalesce(f.any_cross, false) AS any_cross, coalesce(f.any_addr_missing, false) AS any_addr_missing, coalesce(f.any_num_conflict, false) AS any_num_conflict
        FROM read_parquet('{(BENCH / f'queries_{args.name}.parquet').as_posix()}') b
        LEFT JOIN (SELECT q, bool_or(cross_script) any_cross, bool_or(tgt_addr_missing) any_addr_missing, bool_or(number_conflict) any_num_conflict
                   FROM read_parquet('{FLAGS}') GROUP BY q) f ON f.q = b.id""")
    con.execute(f"CREATE TABLE truth AS SELECT q, t FROM read_parquet('{FLAGS}') WHERE q IN (SELECT id FROM bench_q)")
    n_q = con.execute('SELECT count(*) FROM bench_q').fetchone()[0]
    info = json.loads((BENCH / f'cand_{args.name}.json').read_text(encoding='utf-8'))
    result = {'name': args.name, 'queries': n_q, 'query_fold': info['query_fold'], 'corpus_fold': info['corpus_fold'], 'corpus': info['corpus']}
    slices = [('all queries', ''), ('non-singleton queries', 'match_count >= 1'), ('match count 1', "match_count = 1"), ('match count 2', 'match_count = 2'),
              ('match count 3-4', 'match_count BETWEEN 3 AND 4'), ('match count 5+ (high cardinality)', 'match_count >= 5'),
              ('has a cross-script target', 'any_cross'), ('has a target with missing address', 'any_addr_missing'), ('has a target with a conflicting number', 'any_num_conflict')]
    configs = {'v1 exact keys': {c: MAX_K for c in BASELINE}, 'union, sparse k=20': union_spec(20), 'union, sparse k=100': union_spec(100)}
    emb_file = BENCH / f'cand_{args.name}_emb.parquet'
    if emb_file.exists():
        con.execute(f"INSERT INTO cand SELECT channel, q, t, rnk, score FROM read_parquet('{emb_file.as_posix()}')")
        configs.update({'embedding channel alone, k=20': {'emb_name': 20}, 'union k=20 + embedding k=10': {**union_spec(20), 'emb_name': 10},
                        'union k=20 + embedding k=20': {**union_spec(20), 'emb_name': 20}, 'union k=20 + embedding k=50': {**union_spec(20), 'emb_name': 50}})
    result['configs'] = {}
    for cname, spec in configs.items():
        rows = []
        for sname, where in slices:
            for country in ('all', 'India', 'US'):
                m = evaluate.evaluate(con, spec, country, where)
                rows.append({'slice': sname, 'country': country, **m})
        result['configs'][cname] = rows
    curve = []
    for k in (5, 10, 20, 50, 100):
        m = evaluate.evaluate(con, union_spec(k))
        curve.append({'sparse_k': k, **m})
    result['recall_vs_size'] = curve
    result['missed_k20'] = evaluate.missed_by_slice(con, union_spec(20), FLAGS)
    result['missed_k100'] = evaluate.missed_by_slice(con, union_spec(100), FLAGS)
    main_rows = {c: next(r for r in rows if r['slice'] == 'all queries' and r['country'] == 'all') for c, rows in result['configs'].items()}
    k20 = main_rows['union, sparse k=20']
    k100 = main_rows['union, sparse k=100']
    result['gates'] = [
        {'gate': 'micro link recall >= 99%', 'k20': k20['micro_recall'], 'k100': k100['micro_recall'], 'pass_k20': k20['micro_recall'] >= 0.99, 'pass_k100': k100['micro_recall'] >= 0.99},
        {'gate': 'oracle macro-F0.5 >= 0.97', 'k20': k20['oracle_macro_f05'], 'k100': k100['oracle_macro_f05'], 'pass_k20': k20['oracle_macro_f05'] >= 0.97, 'pass_k100': k100['oracle_macro_f05'] >= 0.97},
        {'gate': 'zero-candidate rate <= 0.5%', 'k20': k20['zero_candidate_rate'], 'k100': k100['zero_candidate_rate'], 'pass_k20': k20['zero_candidate_rate'] <= 0.005, 'pass_k100': k100['zero_candidate_rate'] <= 0.005}]
    (OUT / f'retrieval_gates_{args.name}.json').write_text(json.dumps(result, indent=2, default=float) + '\n', encoding='utf-8', newline='\n')

    head = ['| slice | country | queries | micro recall | all-links coverage | macro recall | zero-cand | mean cands (p99) | oracle F0.5 |', '|---|---|---:|---:|---:|---:|---:|---:|---:|']

    def row(r):
        return (f"| {r['slice']} | {r['country']} | {r['queries']:,} | {pct(r['micro_recall'])} | {pct(r['all_links_coverage'])} | {pct(r['macro_recall_nonsingleton'])} | "
                f"{pct(r['zero_candidate_rate'])} | {r['cand_mean']:.1f} ({r['cand_p99']:.0f}) | {r['oracle_macro_f05']:.4f} |")
    md = [f'# Candidate quality gates: `{args.name}` ({n_q:,} queries, query fold `{info["query_fold"]}`, corpus `{info["corpus_fold"]}`)', '',
          f'Corpus sizes: {info["corpus"]}. Generated by `scripts/retrieval_gates.py`. Oracle = a perfect classifier restricted to the candidates (ceiling, not a model score).', '',
          '## Gate verdict', '', '| gate | k=20 | pass | k=100 | pass |', '|---|---:|:-:|---:|:-:|']
    for g in result['gates']:
        fmt = (lambda v: f'{v:.4f}') if 'oracle' in g['gate'] else pct
        md.append(f"| {g['gate']} | {fmt(g['k20'])} | {'yes' if g['pass_k20'] else '**no**'} | {fmt(g['k100'])} | {'yes' if g['pass_k100'] else '**no**'} |")
    md += ['', '## Recall versus candidate-set size (union, sparse channels at k)', '', '| sparse k | micro recall | all-links coverage | mean cands | p99 | oracle F0.5 |', '|---:|---:|---:|---:|---:|---:|']
    md += [f"| {c['sparse_k']} | {pct(c['micro_recall'])} | {pct(c['all_links_coverage'])} | {c['cand_mean']:.1f} | {c['cand_p99']:.0f} | {c['oracle_macro_f05']:.4f} |" for c in curve]
    for cname, rows in result['configs'].items():
        md += ['', f'## {cname}', ''] + head + [row(r) for r in rows]
    k20m = {(r['dimension'], r['value']): r for r in result['missed_k20']}
    k100m = {(r['dimension'], r['value']): r for r in result['missed_k100']}
    md += ['', '## Link-level slices (recall of the union)', '', '| dimension | value | links | k=20 recall | k=100 recall |', '|---|---|---:|---:|---:|']
    md += [f"| {d} | {v} | {r['links']:,} | {pct(r['recall'])} | {pct(k100m[(d, v)]['recall'])} |" for (d, v), r in k20m.items()]
    (OUT / f'retrieval_gates_{args.name}.md').write_text('\n'.join(md) + '\n', encoding='utf-8', newline='\n')
    print('\n'.join(md[:14]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
