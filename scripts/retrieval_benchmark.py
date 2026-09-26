"""Member B / B3 + B4: first retrieval benchmark and channel expansion (protocol A, isolated dev fold).

    python scripts/retrieval_benchmark.py [--queries 10000] [--skip-build]

1. samples 10,000 deterministic dev queries (country x match-count strata, singletons included);
2. per country, builds every candidate channel from the FEATURES ONLY (the connection that generates candidates has no truth relation);
3. evaluates with the labels (recall, all-links coverage, candidate sizes, oracle macro-F0.5) and writes the reports.

Outputs: data/benchmarks/bench_dev10k_v1.parquet, data/benchmarks/candidates_dev10k_v1.parquet,
         reports/eda/retrieval_benchmark.md / .json, reports/eda/retrieval_missed_pairs.csv
"""
import argparse
import json
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from retrieval import MAX_K, engine, evaluate  # noqa: E402

MANIFEST = ROOT / 'data' / 'splits' / 'fold_manifest_v1.parquet'
FEATURES = ROOT / 'data' / 'features' / 'feat_v2_0'
FLAGS = ROOT / 'data' / 'scratch' / 'label_pairs.parquet'
BENCH = ROOT / 'data' / 'benchmarks'
OUT = ROOT / 'reports' / 'eda'
COUNTRIES = ('India', 'US')
EQ_NAMES = [c['name'] for c in engine.EQUALITY_CHANNELS]
SPARSE = [c['name'] for c in engine.POSTINGS_CHANNELS]
GROUP = {c['name']: c['group'] for c in engine.EQUALITY_CHANNELS + engine.POSTINGS_CHANNELS}
# order in which channels are added (B4: one at a time), after the v1 exact-key baseline
ADD_ORDER = ['eq_name_core', 'eq_address_tokset', 'eq_name_compact', 'eq_name_skeleton', 'eq_core_postal', 'eq_core_number', 'eq_skeleton_number',
             'tok_name', 'tri_name', 'tok_address', 'bigram_address']
BASELINE = ['eq_name_key', 'eq_address_key']


def pct(x):
    return f'{100 * x:.2f}%'


def build_candidates(n_queries: int) -> dict:
    BENCH.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET threads=8; SET memory_limit='10GB'")
    digest = engine.sample_queries(con, MANIFEST.as_posix(), n_queries)
    con.execute(f"COPY (SELECT * FROM bench_q ORDER BY id) TO '{(BENCH / 'bench_dev10k_v1.parquet').as_posix()}' (FORMAT PARQUET)")
    strata = con.execute("SELECT country, count(*), count(*) FILTER (WHERE match_count = 0) FROM bench_q GROUP BY 1 ORDER BY 1").fetchall()
    print('benchmark queries:', strata, 'digest', digest[:16], flush=True)
    parts, stats, sizes = [], [], {}
    for country in COUNTRIES:
        started = time.perf_counter()
        glob = (FEATURES / 'split=train' / 'source=*' / f'country={country}' / '*.parquet').as_posix()
        sizes[country] = engine.load_corpus(con, glob, MANIFEST.as_posix(), country)
        print(f'[{country}] {sizes[country]} loaded in {time.perf_counter() - started:.0f}s', flush=True)
        engine.run_all_channels(con, log=lambda m: print(m, flush=True))
        part = (BENCH / f'_cand_{country}.parquet').as_posix()
        con.execute(f"""COPY (SELECT c.channel, q.entity_id AS q, t.entity_id AS t, c.rnk, c.score FROM cand c JOIN bq q USING (qid) JOIN tt t USING (tid)
                         ORDER BY channel, q, rnk) TO '{part}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
        parts.append(part)
        stats += [dict(zip(['channel', 'seconds', 'pairs_before_cap', 'oversize_query_blocks', 'note'], r), country=country)
                  for r in con.execute('SELECT * FROM chan_stats').fetchall()]
        print(f'[{country}] done in {time.perf_counter() - started:.0f}s', flush=True)
    final = BENCH / 'candidates_dev10k_v1.parquet'
    con.execute(f"COPY (SELECT * FROM read_parquet([{', '.join(repr(p) for p in parts)}]) ORDER BY channel, q, rnk) TO '{final.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    for p in parts:
        Path(p).unlink()
    return {'digest': digest, 'strata': strata, 'corpus': sizes, 'channel_stats': stats}


def leakage_checks(con) -> list:
    out = []
    dev_targets = f"(SELECT entity_id FROM read_parquet('{MANIFEST.as_posix()}') WHERE role = 'target' AND fold = 'dev')"
    n = con.execute(f"SELECT count(*) FROM cand WHERE t NOT IN {dev_targets}").fetchone()[0]
    out.append(('every candidate target belongs to the dev fold (protocol A corpus)', n == 0, f'{n} outside'))
    n = con.execute("SELECT count(*) FROM cand WHERE q NOT IN (SELECT id FROM bench_q)").fetchone()[0]
    out.append(('every candidate query is a benchmark query', n == 0, f'{n} unknown'))
    n = con.execute(f"SELECT count(*) FROM bench_q WHERE id NOT IN (SELECT entity_id FROM read_parquet('{MANIFEST.as_posix()}') WHERE role = 'query' AND fold = 'dev')").fetchone()[0]
    out.append(('every benchmark query is a dev-fold query', n == 0, f'{n} outside'))
    n = con.execute("SELECT count(*) - count(DISTINCT (channel, q, t)) FROM cand").fetchone()[0]
    out.append(('no duplicate (channel, query, target) rows', n == 0, f'{n} duplicates'))
    n = con.execute(f"SELECT count(*) FROM cand WHERE rnk < 1 OR rnk > {MAX_K}").fetchone()[0]
    out.append((f'ranks are within 1..{MAX_K}', n == 0))
    n = con.execute("""SELECT count(*) FROM cand c JOIN read_parquet('%s') a ON a.entity_id = c.q JOIN read_parquet('%s') b ON b.entity_id = c.t WHERE a.country <> b.country"""
                    % ((FEATURES / 'split=train' / 'source=1' / 'country=*' / '*.parquet').as_posix(),
                       (FEATURES / 'split=train' / 'source=[23]' / 'country=*' / '*.parquet').as_posix())).fetchone()[0]
    out.append(('no candidate crosses countries', n == 0, f'{n} cross-country'))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--queries', type=int, default=10_000)
    parser.add_argument('--skip-build', action='store_true', help='reuse data/benchmarks/candidates_dev10k_v1.parquet')
    args = parser.parse_args()
    started = time.perf_counter()
    info = {}
    if not args.skip_build:
        info = build_candidates(args.queries)
        (BENCH / 'build_info.json').write_text(json.dumps(info, indent=2, default=float) + '\n', encoding='utf-8', newline='\n')
        print(f'candidates built in {time.perf_counter() - started:.0f}s', flush=True)
    elif (BENCH / 'build_info.json').exists():
        info = json.loads((BENCH / 'build_info.json').read_text(encoding='utf-8'))
    con = duckdb.connect()
    con.execute("SET threads=8; SET memory_limit='10GB'")
    con.execute(f"CREATE TABLE cand AS SELECT * FROM read_parquet('{(BENCH / 'candidates_dev10k_v1.parquet').as_posix()}')")
    con.execute(f"CREATE TABLE bench_q AS SELECT * FROM read_parquet('{(BENCH / 'bench_dev10k_v1.parquet').as_posix()}')")
    con.execute(f"CREATE TABLE truth AS SELECT q, t FROM read_parquet('{FLAGS.as_posix()}') WHERE q IN (SELECT id FROM bench_q)")
    checks = leakage_checks(con)
    for c in checks:
        print(('PASS  ' if c[1] else 'FAIL  ') + c[0] + (f'   [{c[2]}]' if len(c) > 2 and c[2] else ''), flush=True)
    result = {'info': info, 'leakage_checks': [{'name': c[0], 'ok': c[1], 'detail': c[2] if len(c) > 2 else ''} for c in checks]}

    # ---- B3: the baseline row (two exact-key joins, union, provenance kept)
    base = {c: MAX_K for c in BASELINE}
    result['b3_baseline'] = {'all': evaluate.evaluate(con, base), **{c: evaluate.evaluate(con, base, c) for c in COUNTRIES}}
    result['b3_single_channels'] = {c: evaluate.evaluate(con, {c: MAX_K}) for c in BASELINE}
    prov = con.execute("""SELECT count(*) FILTER (WHERE n = 1 AND ch = 'eq_name_key'), count(*) FILTER (WHERE n = 1 AND ch = 'eq_address_key'), count(*) FILTER (WHERE n = 2)
                          FROM (SELECT q, t, count(*) n, any_value(channel) ch FROM cand WHERE channel IN ('eq_name_key', 'eq_address_key') GROUP BY q, t)""").fetchone()
    result['b3_provenance'] = {'name_only': prov[0], 'address_only': prov[1], 'both': prov[2]}
    print('B3 baseline:', {k: (round(v, 4) if isinstance(v, float) else v) for k, v in result['b3_baseline']['all'].items()}, flush=True)

    # ---- B4a: every channel alone at k = 10, 20, 50, 100
    result['channels_by_k'] = {c: {k: evaluate.evaluate(con, {c: k}) for k in (10, 20, 50, 100)} for c in EQ_NAMES + SPARSE}
    # ---- B4b: add one channel at a time (equality channels at 100, sparse channels at k=20 and at k=100)
    for label, sparse_k in (('k20', 20), ('k100', 100)):
        spec = {c: MAX_K for c in BASELINE}
        steps = [('baseline (v1 exact keys)', dict(spec))]
        for ch in ADD_ORDER:
            spec[ch] = MAX_K if ch in EQ_NAMES else sparse_k
            steps.append((f'+ {ch}', dict(spec)))
        result[f'cumulative_{label}'] = [{'step': s, 'channels': dict(sp), **evaluate.evaluate(con, sp)} for s, sp in steps]
        result[f'cumulative_{label}_by_country'] = {c: evaluate.evaluate(con, steps[-1][1], c) for c in COUNTRIES}
        print(label, 'final union:', {k: (round(v, 4) if isinstance(v, float) else v) for k, v in result[f'cumulative_{label}'][-1].items() if k != 'channels'}, flush=True)
    final_spec = result['cumulative_k20'][-1]['channels']
    wide_spec = result['cumulative_k100'][-1]['channels']
    result['missed_baseline'] = evaluate.missed_by_slice(con, base, FLAGS.as_posix())
    result['missed_union_k20'] = evaluate.missed_by_slice(con, final_spec, FLAGS.as_posix())
    result['missed_union_k100'] = evaluate.missed_by_slice(con, wide_spec, FLAGS.as_posix())
    with (OUT / 'retrieval_missed_pairs.csv').open('w', encoding='utf-8', newline='\n') as fh:
        fh.write('config,dimension,value,links,missed,recall\n')
        for cfg, key in (('baseline_v1_exact', 'missed_baseline'), ('union_k20', 'missed_union_k20'), ('union_k100', 'missed_union_k100')):
            for r in result[key]:
                fh.write(f"{cfg},{r['dimension']},{r['value']},{r['links']},{r['missed']},{r['recall']:.6f}\n")
    (OUT / 'retrieval_benchmark.json').write_text(json.dumps(result, indent=2, default=float) + '\n', encoding='utf-8', newline='\n')
    write_markdown(result)
    print(f'done in {time.perf_counter() - started:.0f}s', flush=True)
    return 0 if all(c[1] for c in checks) else 1


def write_markdown(result: dict) -> None:
    def row(name, m):
        return (f"| {name} | {pct(m['micro_recall'])} | {pct(m['all_links_coverage'])} | {pct(m['macro_recall_nonsingleton'])} | {pct(m['zero_candidate_rate'])} | "
                f"{m['pairs']:,} | {m['cand_mean']:.1f} | {m['cand_p50']:.0f} / {m['cand_p90']:.0f} / {m['cand_p99']:.0f} / {m['cand_max']} | {m['oracle_macro_f05']:.4f} |")
    head = ['| config | micro link recall | all-links coverage | macro recall (non-singleton) | zero-candidate rate | pairs | mean cands | p50 / p90 / p99 / max | oracle macro-F0.5 |',
            '|---|---:|---:|---:|---:|---:|---:|---|---:|']
    b = result['b3_baseline']
    md = ['# Retrieval benchmark (protocol A, dev fold, 10,000 queries)', '',
          'Generated by `scripts/retrieval_benchmark.py`. The corpus of each query is the **dev-fold targets of its country** (about 3.3M India, 5.0M US); '
          'candidates are generated from features only and the labels enter only in the evaluator. Metrics are over all sampled queries including singletons and zero-candidate '
          'queries. **Oracle macro-F0.5** = the score of a perfect classifier restricted to these candidates (true links in the candidate set are predicted, everything else rejected, '
          'singletons predicted empty). It is a ceiling, not a model score. Protocol A is easier than the test-time corpus (10M targets); see the full-corpus stress test in the validation protocol.', '',
          f"Benchmark queries: {sum(s[1] for s in result['info'].get('strata', []))} ({', '.join(f'{c}: {n} incl. {z} singletons' for c, n, z in result['info'].get('strata', []))}); corpus: {result['info'].get('corpus')}.", '',
          '## B3 - baseline: exact `(country, name_key)` and `(country, address_key)` joins', ''] + head
    md += [row('union, all', b['all']), row('union, India', b['India']), row('union, US', b['US']),
           row('name_key alone', result['b3_single_channels']['eq_name_key']), row('address_key alone', result['b3_single_channels']['eq_address_key'])]
    pv = result['b3_provenance']
    md += ['', f"Provenance of the union's pairs: name only {pv['name_only']:,}, address only {pv['address_only']:,}, both {pv['both']:,}. Blocks larger than {MAX_K} candidates are ranked by a secondary "
           "similarity (address token Jaccard for name blocks, name similarity for address blocks) before truncation; empty keys never join. The audit's uncapped exact-key link recall is 28.80%.", '',
           '## B4 - channels added one at a time', '', 'Equality channels keep up to 100 candidates per query; sparse channels (IDF-weighted inverted-index postings) are shown with k = 20 and k = 100 per channel. Candidates of different channels are unioned, never re-ranked against each other.', '']
    for label in ('k20', 'k100'):
        md += [f'### Cumulative union, sparse channels at k = {label[1:]}', ''] + head
        md += [row(s['step'], s) for s in result[f'cumulative_{label}']]
        md += ['']
    md += ['## Each channel alone by k', ''] + [head[0].replace('| config', '| channel, k'), head[1]]
    for c, by_k in result['channels_by_k'].items():
        for k, m in by_k.items():
            md.append(row(f'{c}, k={k}', m))
    md += ['', '## Missed links by slice', '', 'Per slice: links of the benchmark queries, how many the union misses, recall. Configurations: v1 exact-key baseline, final union at k = 20 and k = 100 '
           '(full table in `retrieval_missed_pairs.csv`).', '', '| dimension | value | links | baseline recall | union k=20 recall | union k=100 recall |', '|---|---|---:|---:|---:|---:|']
    k20 = {(r['dimension'], r['value']): r for r in result['missed_union_k20']}
    k100 = {(r['dimension'], r['value']): r for r in result['missed_union_k100']}
    for r in result['missed_baseline']:
        key = (r['dimension'], r['value'])
        md.append(f"| {r['dimension']} | {r['value']} | {r['links']:,} | {pct(r['recall'])} | {pct(k20[key]['recall'])} | {pct(k100[key]['recall'])} |")
    md += ['', '## Channel cost', '', '| channel | country | seconds | pairs before cap | queries with an oversize block | note |', '|---|---|---:|---:|---:|---|']
    md += [f"| {s['channel']} | {s['country']} | {s['seconds']:.1f} | {s['pairs_before_cap']:,} | {s['oversize_query_blocks']:,} | {s['note']} |" for s in result['info'].get('channel_stats', [])]
    md += ['', '## Leakage and integrity checks', ''] + [f"- {'PASS' if c['ok'] else '**FAIL**'} {c['name']}" + (f" ({c['detail']})" if c['detail'] else '') for c in result['leakage_checks']]
    (OUT / 'retrieval_benchmark.md').write_text('\n'.join(md) + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    sys.exit(main())
