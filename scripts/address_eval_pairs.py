"""Phase 5 evaluation on the deterministic 0.5% positive-pair sample (reports/eda/positive_pair_sample_s2/s3.csv).

    python scripts/address_eval_pairs.py

EXPLORATORY and recall-side only (true pairs). Labels are used to REPORT agreement and to compare a few named design variants; no
lexicon entry was derived from them (the lexicons come from the unlabeled census). Denominator: pairs with a non-empty target address.

Reported per group (S2/S3 x India/US): exact agreement of v1 key, canonical view, token set, segment set; token-set Jaccard;
state agreement; number agreement/conflict; city-candidate overlap; and the effect of two design variants
(keep number labels such as ``No``; do not remove injected components). The defaults drop labels and remove injected components..
"""
import csv
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from unittest import mock  # noqa: E402

from cleaning import addresses as A  # noqa: E402
from cleaning import lexicons as L  # noqa: E402
from cleaning import translit as T  # noqa: E402
from normalization import comparison_key  # noqa: E402

OUT = ROOT / 'reports' / 'cleaning'


def jaccard(a: str, b: str) -> float:
    x, y = set(a.split()), set(b.split())
    return len(x & y) / len(x | y) if x | y else 0.0


def pct(n, d):
    return f'{100 * n / d:.1f}%' if d else 'n/a'


def ablation_patches():
    """Named rule groups; each variant switches ONE group off (everything else stays at the default)."""
    def without_multi(country):
        return {k: v for k, v in L.address_abbrev(country).items() if v[1] != 'suffix_multi'}
    return {
        'ct/hwy suffix_multi abbreviations': [mock.patch.object(A, 'address_abbrev', without_multi)],
        'India injected components (hn, b3, region, divreportingcircle)': [
            mock.patch.object(A, 'address_noise_number_tokens', lambda c: frozenset()),
            mock.patch.object(A, 'address_noise_segment_words', lambda c: frozenset()),
            mock.patch.object(A, 'address_noise_tokens', lambda c: L.address_noise_tokens(c) - {'b3'}),
            mock.patch.object(A, 'address_placeholder_segments', lambda c='': L.address_placeholder_segments(c) - {'divreportingcircle'})],
        'number label across a comma (Plot No, 93)': [mock.patch.object(A, '_drop_labels_across_segments', lambda lists: [t for t in lists if t])],
    }


def ablation_table(groups):
    names = [f'{s}-{c}' for s, c in groups]
    lines = ['', '## Rule ablation on true pairs (each row switches one group OFF)', '',
             'Token-set equality / token-set Jaccard >= 0.8 / median Jaccard, on the same pairs. The row "default" is the shipped configuration.', '',
             '| variant | ' + ' | '.join(names) + ' |', '|---|' + '---:|' * len(names)]
    variants = {'default': []}
    variants.update({f'without {k}': v for k, v in ablation_patches().items()})
    for label, patches in variants.items():
        cells = []
        for key in groups:
            rows, country = groups[key], key[1]
            equal = high = 0
            jac = []
            for patch in patches:
                patch.start()
            try:
                for r in rows:
                    a = A.build_address_features(r['s1_address'], country)['address_tokset']
                    b = A.build_address_features(r['target_address'], country)['address_tokset']
                    equal += a == b != ''
                    j = jaccard(a, b)
                    high += j >= 0.8
                    jac.append(j)
            finally:
                for patch in patches:
                    patch.stop()
            cells.append(f'{pct(equal, len(rows))} / {pct(high, len(rows))} / {statistics.median(jac):.3f}')
        lines.append(f'| {label} | ' + ' | '.join(cells) + ' |')
    return lines


def main() -> int:
    groups = {}
    for src in ('s2', 's3'):
        rows = list(csv.DictReader((ROOT / f'reports/eda/positive_pair_sample_{src}.csv').open(encoding='utf-8')))
        for country in ('India', 'US'):
            groups[(src.upper(), country)] = [r for r in rows if r['country'] == country and r['target_address'].strip()]
    table = {}
    extra = {}
    for (src, country), rows in groups.items():
        name = f'{src}-{country}'
        tally = Counter()
        jac = {'canon': [], 'drop_labels': [], 'keep_extras': []}
        for r in rows:
            a = A.build_address_features(r['s1_address'], country)
            b = A.build_address_features(r['target_address'], country)
            tally['n'] += 1
            tally['v1 address_key'] += comparison_key(r['s1_address']) == comparison_key(r['target_address'])
            tally['address_canon'] += a['address_canon'] == b['address_canon'] != ''
            tally['address_tokset'] += a['address_tokset'] == b['address_tokset'] != ''
            tally['address_segset'] += a['address_segset'] == b['address_segset'] != ''
            j = jaccard(a['address_tokset'], b['address_tokset'])
            jac['canon'].append(j)
            tally['tokset Jaccard >= 0.8'] += j >= 0.8
            # state
            if a['address_state_canon'] and b['address_state_canon']:
                tally['state: both found and equal'] += a['address_state_canon'] == b['address_state_canon']
                tally['state: both found and DIFFERENT'] += a['address_state_canon'] != b['address_state_canon']
            elif not b['address_state_canon']:
                tally['state: target has none'] += 1
            # numbers (canonical spans)
            na, nb = set(a['address_numbers_canon']), set(b['address_numbers_canon'])
            if na and nb:
                tally['numbers: both have some'] += 1
                tally['numbers: share at least one'] += bool(na & nb)
                tally['numbers: conflict (none shared)'] += not (na & nb)
            # cities
            ca, cb = set(a['address_city_candidates']), set(b['address_city_candidates'])
            tally['city candidates overlap'] += bool(ca & cb)
            # remaining native-script tokens after canonicalisation
            if country == 'India':
                tally['target canon still has non-Latin tokens'] += any(not t.isascii() and T.script_mask(t) for t in b['address_canon'].split())
            # variants
            a2, b2 = A.build_address_features(r['s1_address'], country, drop_labels=False), A.build_address_features(r['target_address'], country, drop_labels=False)
            jac['drop_labels'].append(jaccard(a2['address_tokset'], b2['address_tokset']))
            tally['variant KEEP number labels: tokset equal'] += a2['address_tokset'] == b2['address_tokset'] != ''
            a3, b3 = A.build_address_features(r['s1_address'], country, remove_extras=False), A.build_address_features(r['target_address'], country, remove_extras=False)
            jac['keep_extras'].append(jaccard(a3['address_tokset'], b3['address_tokset']))
            tally['variant keep injected components: tokset equal'] += a3['address_tokset'] == b3['address_tokset'] != ''
        table[name] = tally
        extra[name] = {k: statistics.median(v) for k, v in jac.items()}
        extra[name].update({'p10 canon': sorted(jac['canon'])[len(jac['canon']) // 10]})
    cols = list(groups)
    names = [f'{s}-{c}' for s, c in cols]
    lines = ['# Address view agreement on true pairs (exploratory, recall side)', '',
             'Exact agreement / rates on the 0.5% deterministic positive-pair sample; denominator = pairs with a non-empty target address. '
             'Labels are used to report, not to fit: lexicons come from the unlabeled census.', '',
             '| metric | ' + ' | '.join(names) + ' |', '|---|' + '---:|' * len(names)]
    lines.append('| pairs | ' + ' | '.join(str(table[n]['n']) for n in names) + ' |')
    for key in ['v1 address_key', 'address_canon', 'address_tokset', 'address_segset', 'tokset Jaccard >= 0.8']:
        lines.append(f'| {key} | ' + ' | '.join(pct(table[n][key], table[n]['n']) for n in names) + ' |')
    lines.append('| median tokset Jaccard | ' + ' | '.join(f"{extra[n]['canon']:.2f}" for n in names) + ' |')
    lines.append('| p10 tokset Jaccard | ' + ' | '.join(f"{extra[n]['p10 canon']:.2f}" for n in names) + ' |')
    lines += ['| **state** | ' + ' | '.join('' for _ in names) + ' |']
    for key in ['state: both found and equal', 'state: both found and DIFFERENT', 'state: target has none']:
        lines.append(f'| {key} | ' + ' | '.join(pct(table[n][key], table[n]['n']) for n in names) + ' |')
    lines += ['| **numbers** (pairs where both have spans) | ' + ' | '.join(str(table[n]['numbers: both have some']) for n in names) + ' |']
    for key in ['numbers: share at least one', 'numbers: conflict (none shared)']:
        lines.append(f'| {key} | ' + ' | '.join(pct(table[n][key], table[n]['numbers: both have some']) for n in names) + ' |')
    lines.append('| city candidates overlap | ' + ' | '.join(pct(table[n]['city candidates overlap'], table[n]['n']) for n in names) + ' |')
    lines.append('| India: target canon still has non-Latin tokens | ' + ' | '.join(pct(table[n]['target canon still has non-Latin tokens'], table[n]['n']) if 'India' in n else '' for n in names) + ' |')
    lines += ['| **variants** | ' + ' | '.join('' for _ in names) + ' |']
    for key, jkey in [('variant KEEP number labels: tokset equal', 'drop_labels'), ('variant keep injected components: tokset equal', 'keep_extras')]:
        lines.append(f'| {key} | ' + ' | '.join(pct(table[n][key], table[n]['n']) for n in names) + ' |')
        lines.append(f'| &nbsp;&nbsp;median Jaccard | ' + ' | '.join(f"{extra[n][jkey]:.2f}" for n in names) + ' |')
    lines += ablation_table(groups)
    text = '\n'.join(lines) + '\n'
    (OUT / 'address_pair_agreement.md').write_text(text, encoding='utf-8', newline='\n')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
