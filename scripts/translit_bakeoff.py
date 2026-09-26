"""Phase 4 transliteration bake-off on India cross-script true pairs.

    python scripts/translit_bakeoff.py                                   # PROVISIONAL: deterministic 5% pair sample
    python scripts/translit_bakeoff.py --fold-manifest PATH --fold dev   # restrict to Member B's development fold

PROVISIONAL until B freezes a fold: the sample is `hash(source1_entity_id, target_id) % 20 = 0` over ALL train labels, so it
can overlap what later becomes a validation/holdout fold. Only a handful of engine/variant choices are made from it (no learned
mapping), and the script should be re-run with --fold-manifest once B's manifest exists.

For every pair the reference S1 core and the native-script target core (legal forms already removed, including the native
legal tier) are rendered to ASCII by an engine and reduced by the same skeleton function; we report, per script:
  ratio distribution (RapidFuzz ratio of the two skeletons), share >= 80 and >= 90, exact equality,
  and for the equality channel: recall and how many S1 India names share the target's key (ambiguity).
Also reported: the v1-key baseline, runtime per name, and the share of S1 names that share a skeleton key.
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

import duckdb  # noqa: E402
from anyascii import anyascii  # noqa: E402
from rapidfuzz import fuzz  # noqa: E402

from cleaning import names as N  # noqa: E402
from cleaning import translit as T  # noqa: E402
from cleaning.manifest import TRUTH_COLUMNS, duckdb_csv_scan  # noqa: E402
from normalization import comparison_key  # noqa: E402

OUT = ROOT / 'reports' / 'cleaning'
INTERIM = ROOT / 'data' / 'interim'
INDIC_CLASS = '[' + ''.join(f'\\p{{{s}}}' for s in T.INDIC_SCRIPTS) + ']'

try:
    from indic_transliteration import sanscript
    SANSCRIPT = {'Devanagari': sanscript.DEVANAGARI, 'Bengali': sanscript.BENGALI, 'Gurmukhi': sanscript.GURMUKHI, 'Gujarati': sanscript.GUJARATI,
                 'Oriya': sanscript.ORIYA, 'Tamil': sanscript.TAMIL, 'Telugu': sanscript.TELUGU, 'Kannada': sanscript.KANNADA,
                 'Malayalam': sanscript.MALAYALAM}
    SCHEMES = {'itrans': sanscript.ITRANS, 'hk': sanscript.HK, 'iast': sanscript.IAST}
except ImportError:   # optional candidate (requirements-bakeoff.txt)
    SANSCRIPT, SCHEMES = {}, {}


def indic_engine(scheme):
    def render(core: str) -> str:
        out = []
        for token in core.split():
            mask = T.script_mask(token)
            script = next((s for s in T.INDIC_SCRIPTS if mask & T.SCRIPT_BITS[s]), None)
            out.append(anyascii(sanscript.transliterate(token, SANSCRIPT[script], SCHEMES[scheme])).lower() if script else anyascii(token))
        return ' '.join(out)
    return render


ENGINES = {'anyascii': lambda core: T.to_ascii(core, 'anyascii'), 'anyascii_n': lambda core: T.to_ascii(core, 'anyascii_n')}
for _name in SCHEMES:
    ENGINES[_name] = indic_engine(_name)
VARIANTS = {'base': False, 'coarse': True}


def load_pairs(fold_manifest, fold):
    con = duckdb.connect()
    con.execute("SET memory_limit='4GB'")
    con.execute('SET threads=4')
    truth = ROOT / 'student_resource' / 'dataset' / 'train' / 'train_ground_truth.tsv'
    con.execute(f'CREATE TEMP TABLE truth AS SELECT * FROM {duckdb_csv_scan(truth, TRUTH_COLUMNS)}')
    con.execute("CREATE TEMP TABLE pairs AS SELECT source1_entity_id, unnest(string_split(matched_entity_ids, ',')) AS target_id FROM truth WHERE matched_entity_ids<>''")
    fold_join = ''
    if fold_manifest:
        con.execute(f"CREATE TEMP TABLE folds AS SELECT * FROM read_parquet('{Path(fold_manifest).as_posix()}')")
        fold_join = f"JOIN folds f ON f.source1_entity_id = p.source1_entity_id AND f.fold = '{fold}'"
    sample = '' if fold_manifest else 'AND hash(p.source1_entity_id, p.target_id) % 20 = 0'
    rows = []
    for source in (2, 3):
        rows += con.execute(f"""SELECT p.source1_entity_id, a.business_name, p.target_id, b.business_name, {source}
            FROM pairs p JOIN read_parquet('{(INTERIM / 'train_source1.parquet').as_posix()}') a ON a.entity_id = p.source1_entity_id
            JOIN read_parquet('{(INTERIM / f'train_source{source}.parquet').as_posix()}') b ON b.entity_id = p.target_id {fold_join}
            WHERE a.country = 'India' AND regexp_matches(b.business_name, '{INDIC_CLASS}') {sample}""").fetchall()
    s1_names = [r[0] for r in con.execute(f"SELECT business_name FROM read_parquet('{(INTERIM / 'train_source1.parquet').as_posix()}') WHERE country='India'").fetchall()]
    con.close()
    return rows, s1_names


def pct(n, d):
    return round(100 * n / d, 1) if d else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--fold-manifest')
    parser.add_argument('--fold', default='dev')
    parser.add_argument('--limit', type=int, default=0, help='cap number of pairs (smoke run; writes nothing)')
    args = parser.parse_args()
    provisional = not args.fold_manifest
    print('loading pairs ...', flush=True)
    pairs, s1_names = load_pairs(args.fold_manifest, args.fold)
    if args.limit:
        pairs = pairs[:args.limit]
        s1_names = s1_names[:args.limit * 20]
    print(f'{len(pairs):,} cross-script India pairs; {len(s1_names):,} S1 India names for the ambiguity index', flush=True)

    # S1 cores and the S1 skeleton index (Latin names, engine-independent)
    s1_core = {}
    def core_of(name):
        c = s1_core.get(name)
        if c is None:
            c = s1_core[name] = N.build_name_features(name, 'India')['name_core']
        return c
    index = {v: Counter() for v in VARIANTS}
    for name in s1_names:
        core = core_of(name)
        for v, coarse in VARIANTS.items():
            index[v][T.skeleton(core, coarse)] += 1
    n_s1 = len(s1_names)
    s1_sharing = {v: pct(sum(c for c in index[v].values() if c > 1), n_s1) for v in VARIANTS}
    s1_core_sharing = pct(sum(c for c in Counter(core_of(n) for n in s1_names).values() if c > 1), n_s1)
    print('S1 rows sharing a key: core', s1_core_sharing, s1_sharing, flush=True)

    # targets: features once
    records = []
    for s1_id, s1_name, t_id, t_name, source in pairs:
        f = N.build_name_features(t_name, 'India')
        script = next((s for s in T.script_names(f['name_scripts']) if s != 'Latin'), 'Other')
        records.append({'s1_core': core_of(s1_name), 't_core': f['name_core'], 'script': script, 's1_name': s1_name, 't_name': t_name, 'source': source,
                        'legal_equal': N.build_name_features(s1_name, 'India')['legal_form'] == f['legal_form']})
    scripts = sorted({r['script'] for r in records})
    counts = Counter(r['script'] for r in records)

    results = {}
    baseline = sorted(fuzz.ratio(comparison_key(r['s1_name']), comparison_key(r['t_name'])) for r in records)
    results['baseline_v1_key_ratio'] = {'p10': baseline[len(baseline) // 10], 'p50': baseline[len(baseline) // 2], 'p90': baseline[9 * len(baseline) // 10]}
    for engine, render in ENGINES.items():
        t0 = time.perf_counter()
        rendered = [render(r['t_core']) for r in records]
        micros = 1e6 * (time.perf_counter() - t0) / len(records)
        for variant, coarse in VARIANTS.items():
            key = f'{engine}|{variant}'
            tally = {s: Counter() for s in scripts + ['ALL']}
            cand_lists = {s: [] for s in scripts + ['ALL']}
            ratios = {s: [] for s in scripts + ['ALL']}
            for r, text in zip(records, rendered):
                a, b = T.skeleton(T.to_ascii(r['s1_core']), coarse), T.skeleton(text, coarse)
                ratio = fuzz.ratio(a, b)
                exact = a == b and a != ''
                cands = index[variant].get(b, 0) if exact else 0
                for s in (r['script'], 'ALL'):
                    ratios[s].append(ratio)
                    tally[s]['n'] += 1
                    tally[s]['ge80'] += ratio >= 80
                    tally[s]['ge90'] += ratio >= 90
                    tally[s]['exact'] += exact
                    if exact:
                        tally[s]['cands'] += cands
                        cand_lists[s].append(cands)
            per = {}
            for s in scripts + ['ALL']:
                rs = sorted(ratios[s])
                t = tally[s]
                cl = sorted(cand_lists[s])
                per[s] = {'n': t['n'], 'p10': rs[len(rs) // 10], 'p50': rs[len(rs) // 2], 'ge80_pct': pct(t['ge80'], t['n']), 'ge90_pct': pct(t['ge90'], t['n']),
                          'exact_pct': pct(t['exact'], t['n']), 'mean_s1_rows_per_exact_key': round(t['cands'] / t['exact'], 2) if t['exact'] else None,
                          'median_s1_rows_per_exact_key': cl[len(cl) // 2] if cl else None, 'p95_s1_rows_per_exact_key': cl[int(0.95 * (len(cl) - 1))] if cl else None,
                          'unique_key_pct_of_exact_hits': pct(sum(1 for c in cl if c == 1), len(cl))}
            results[key] = {'microseconds_per_name': round(micros, 1), 'per_script': per}
            print(f"{key:20s} {micros:6.1f} us/name  ALL: p50={per['ALL']['p50']} ge80={per['ALL']['ge80_pct']}% exact={per['ALL']['exact_pct']}% keyshare={per['ALL']['mean_s1_rows_per_exact_key']}", flush=True)

    summary = {'provisional_sample_not_a_fold': provisional, 'fold_manifest': args.fold_manifest, 'pairs': len(pairs), 'scripts': dict(counts),
               's1_india_names': n_s1, 's1_rows_sharing_a_key_percent': {'name_core': s1_core_sharing, **{f'skeleton_{v}': p for v, p in s1_sharing.items()}},
               'legal_form_equal_percent': pct(sum(r['legal_equal'] for r in records), len(records)),
               'candidates_note': 'indic-transliteration engines present only if installed' if not SCHEMES else 'all engines present', 'results': results}
    if args.limit:
        print('smoke run: nothing written')
        return 0
    (OUT / 'translit_bakeoff.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    lines = ['# Transliteration bake-off (India cross-script true pairs)', '',
             ('**PROVISIONAL**: no fold manifest exists yet. Sample = deterministic 5% of all train labels; re-run with `--fold-manifest` on B\'s dev fold.'
              if provisional else f'Restricted to fold `{args.fold}` of `{args.fold_manifest}`.'), '',
             f'{len(pairs):,} pairs; baseline v1-key ratio p10/p50/p90 = {results["baseline_v1_key_ratio"]["p10"]:.0f}/{results["baseline_v1_key_ratio"]["p50"]:.0f}/'
             f'{results["baseline_v1_key_ratio"]["p90"]:.0f}. Legal form (canonical code) agrees on {summary["legal_form_equal_percent"]}% of pairs.', '',
             f'S1 India names sharing a key with another S1 name: name_core {s1_core_sharing}%, skeleton base {s1_sharing["base"]}%, coarse {s1_sharing["coarse"]}%.', '',
             '## Overall (all scripts)', '',
             'Ambiguity of the skeleton-equality channel = how many S1 India names share the key of an exact hit (mean / median / p95) and the share of hits whose key is unique among S1.', '',
             '| engine | variant | us/name | p10 | p50 | >=80 | >=90 | exact | S1 rows per exact key mean/median/p95 | unique-key hits |', '|---|---|---:|---:|---:|---:|---:|---:|---|---:|']
    for key, res in results.items():
        if key == 'baseline_v1_key_ratio':
            continue
        engine, variant = key.split('|')
        a = res['per_script']['ALL']
        lines.append(f"| {engine} | {variant} | {res['microseconds_per_name']} | {a['p10']:.1f} | {a['p50']:.1f} | {a['ge80_pct']}% | {a['ge90_pct']}% | {a['exact_pct']}% | "
                     f"{a['mean_s1_rows_per_exact_key']} / {a['median_s1_rows_per_exact_key']} / {a['p95_s1_rows_per_exact_key']} | {a['unique_key_pct_of_exact_hits']}% |")
    for key in ('anyascii|base', 'anyascii|coarse'):
        lines += ['', f'## Per script: {key}', '', '| script | pairs | p50 | >=80 | >=90 | exact |', '|---|---:|---:|---:|---:|---:|']
        for s in scripts:
            a = results[key]['per_script'][s]
            lines.append(f"| {s} | {a['n']} | {a['p50']} | {a['ge80_pct']}% | {a['ge90_pct']}% | {a['exact_pct']}% |")
    (OUT / 'translit_bakeoff.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    print('wrote translit_bakeoff.md / .json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
