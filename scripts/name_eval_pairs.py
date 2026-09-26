"""Phase 3 evaluation on the deterministic 0.5% positive-pair sample (reports/eda/positive_pair_sample_s2/s3.csv).

    python scripts/name_eval_pairs.py

EXPLORATORY: recall-side only (exact agreement on TRUE pairs). It says nothing about false candidates; the collision
side is measured in reports/cleaning/name_view_collisions.csv. Labels are used to REPORT agreement and to compare a few
named design variants; no lexicon entry was derived from them. Denominator: pairs whose target name is Latin-script only
(native-script targets belong to Phase 4).

Variants compared (same production code except where stated):
  v1 key, name_hyg, name_core, name_core_fold, name_core_set, name_core_compact, any-of-core-views,
  X1  bracket text DROPPED from the core (the rule the prototype used),
  X2  trailing appended-noise nouns trimmed from the core (candidates derived from unlabeled S1-vs-S2/S3 frequency lift),
  X3  alias-aware: the part after d/b/a (or a/k/a ...) of the target is compared with the reference core.
"""
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

import duckdb  # noqa: E402

from cleaning import names as N  # noqa: E402
from cleaning import text_hygiene as h  # noqa: E402
from cleaning.lexicons import appended_noise, legal_index  # noqa: E402
from normalization import comparison_key  # noqa: E402

OUT = ROOT / 'reports' / 'cleaning'
CENSUS = OUT / 'name_token_census' / 'first_last_tokens.csv'


def core_variant(raw, country, drop_brackets=False, trim=None):
    cleaned, _ = h.clean_text(raw, join_legal_acronyms=True)
    if drop_brackets:
        cleaned = N._BRACKET_GROUP.sub(' ', cleaned)
    f = N.build_name_features(raw, country, cleaned=cleaned)
    core = f['name_core'].split()
    if trim:
        while len(core) > 1 and core[-1] in trim:
            core.pop()
    return ' '.join(core)


def main() -> int:
    lines = ['# Name view agreement on true pairs (exploratory)', '',
             'Exact agreement between the Source 1 reference name and its matched target name, 0.5% deterministic positive-pair sample. '
             '**Recall-side only**: collisions are in `name_view_collisions.csv`. Latin-script targets only.', '',
             'X2 uses the shipped `appended_noise.tsv` (last-position share in S2/S3 >= 5x the S1 share and >= 3000 occurrences; unlabeled; '
             'fitted on train text for US/India and unlabeled test text for France).', '']
    for country in ('India', 'US', 'France'):
        lines.append(f'- {country}: {len(appended_noise(country))} tokens')
    lines.append('')
    header = ['view', 'S2-India', 'S2-US', 'S3-India', 'S3-US']
    table = defaultdict(dict)
    groups = {}
    for src in ('s2', 's3'):
        rows = list(csv.DictReader((ROOT / f'reports/eda/positive_pair_sample_{src}.csv').open(encoding='utf-8')))
        for country in ('India', 'US'):
            groups[(src.upper(), country)] = [r for r in rows if r['country'] == country and not re.search(r'[^\u0000-ɏ]', r['target_name'])]
    for key, g in groups.items():
        name = f'{key[0]}-{key[1]}'
        feats = [(N.build_name_features(r['s1_name'], key[1]), N.build_name_features(r['target_name'], key[1]), r) for r in g]
        tally = Counter()
        for a, b, r in feats:
            s1, tg = r['s1_name'], r['target_name']
            eq = lambda x, y: x == y and x != ''
            tally['v1 name_key'] += eq(comparison_key(s1), comparison_key(tg))
            tally['name_hyg'] += eq(h.hygiene_record(s1, '')['name_hyg'], h.hygiene_record(tg, '')['name_hyg'])
            tally['name_core'] += eq(a['name_core'], b['name_core'])
            tally['name_core_fold'] += eq(a['name_core_fold'], b['name_core_fold'])
            tally['name_core_set'] += eq(a['name_core_set'], b['name_core_set'])
            tally['name_core_compact'] += eq(a['name_core_compact'], b['name_core_compact'])
            any_core = any(eq(a[k], b[k]) for k in ('name_core', 'name_core_fold', 'name_core_set', 'name_core_compact'))
            tally['ANY of the four core views'] += any_core
            x1 = eq(core_variant(s1, key[1], True), core_variant(tg, key[1], True))
            tally['X1 brackets dropped from core'] += x1
            trim = appended_noise(key[1])
            tally['X2 trailing appended-noise trimmed'] += eq(core_variant(s1, key[1], trim=trim), core_variant(tg, key[1], trim=trim))
            tally['X3 alias-aware (any core view OR alias part)'] += any_core or eq(a['name_core'], b['name_alias_right'])
            tally['legal_form equal (info)'] += (a['legal_form'] == b['legal_form'])
        for view, n in tally.items():
            table[view][name] = f'{100 * n / len(g):.1f}%'
        table['pairs (Latin targets)'][name] = str(len(g))
        alias_pairs = sum(1 for _a, b, _r in feats if b['name_alias_marker'])
        table['pairs whose target has an alias marker'][name] = str(alias_pairs)
    lines += ['| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)]
    order = ['pairs (Latin targets)', 'v1 name_key', 'name_hyg', 'name_core', 'name_core_fold', 'name_core_set', 'name_core_compact',
             'ANY of the four core views', 'X1 brackets dropped from core', 'X2 trailing appended-noise trimmed',
             'X3 alias-aware (any core view OR alias part)', 'legal_form equal (info)', 'pairs whose target has an alias marker']
    for view in order:
        lines.append(f'| {view} | ' + ' | '.join(table[view].get(f'{s}-{c}', '') for s in ('S2', 'S3') for c in ('India', 'US')) + ' |')
    text = '\n'.join(lines) + '\n'
    (OUT / 'name_pair_agreement.md').write_text(text, encoding='utf-8', newline='\n')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
