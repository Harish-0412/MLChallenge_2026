"""Phase 5: write the address lexicons from curated definitions plus measured counts.

    python scripts/build_address_lexicons.py            # report only
    python scripts/build_address_lexicons.py --write    # writes src/cleaning/lexicon_data/{states,address_abbrev,address_noise}.tsv

Definitions (which states, which abbreviations) are curated below from the unlabeled census in reports/cleaning/address_census/
and the segment enumeration recorded in reports/eda/cleaning_decisions.md. Counts are measured here. **An entry is written only if
the data supports it** (whole-segment occurrences for states, token counts and lift for abbreviations), so every row carries its
evidence and nothing unobserved can mis-fire. Labels are never read. Fitting corpus: TRAIN text for US/India, unlabeled TEST text for
France (no French training data exists).
"""
import argparse
import csv
import sys
import unicodedata
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / 'data' / 'interim'
LEXICON_DIR = ROOT / 'src' / 'cleaning' / 'lexicon_data'
CENSUS = ROOT / 'reports' / 'cleaning' / 'address_census' / 'tokens.csv'
MIN_STATE_OBSERVATIONS = 50
MIN_DEPARTMENT_OBSERVATIONS = 1000
SPLIT = {'US': 'train', 'India': 'train', 'France': 'test'}

US_STATES = {
    'al': 'alabama', 'ak': 'alaska', 'az': 'arizona', 'ar': 'arkansas', 'ca': 'california', 'co': 'colorado', 'ct': 'connecticut', 'de': 'delaware',
    'dc': 'district of columbia', 'fl': 'florida', 'ga': 'georgia', 'hi': 'hawaii', 'id': 'idaho', 'il': 'illinois', 'in': 'indiana', 'ia': 'iowa',
    'ks': 'kansas', 'ky': 'kentucky', 'la': 'louisiana', 'me': 'maine', 'md': 'maryland', 'ma': 'massachusetts', 'mi': 'michigan', 'mn': 'minnesota',
    'ms': 'mississippi', 'mo': 'missouri', 'mt': 'montana', 'ne': 'nebraska', 'nv': 'nevada', 'nh': 'new hampshire', 'nj': 'new jersey',
    'nm': 'new mexico', 'ny': 'new york', 'nc': 'north carolina', 'nd': 'north dakota', 'oh': 'ohio', 'ok': 'oklahoma', 'or': 'oregon',
    'pa': 'pennsylvania', 'ri': 'rhode island', 'sc': 'south carolina', 'sd': 'south dakota', 'tn': 'tennessee', 'tx': 'texas', 'ut': 'utah',
    'vt': 'vermont', 'va': 'virginia', 'wa': 'washington', 'wv': 'west virginia', 'wi': 'wisconsin', 'wy': 'wyoming',
}
# India: the data contains exactly 16 states (S1 has 16 English names, S3 has 16 two-letter codes, S2/S3 carry 16 native-script forms).
# (code, canonical English name, native-script form)
INDIA = [
    ('mh', 'maharashtra', 'महाराष्ट्र'), ('dl', 'delhi', 'दिल्ली'), ('up', 'uttar pradesh', 'उत्तर प्रदेश'), ('ka', 'karnataka', 'ಕರ್ನಾಟಕ'),
    ('tn', 'tamil nadu', 'தமிழ்நாடு'), ('wb', 'west bengal', 'পশ্চিমবঙ্গ'), ('gj', 'gujarat', 'ગુજરાત'), ('tg', 'telangana', 'తెలంగాణ'),
    ('hr', 'haryana', 'हरियाणा'), ('rj', 'rajasthan', 'राजस्थान'), ('kl', 'kerala', 'കേരളം'), ('br', 'bihar', 'बिहार'),
    ('mp', 'madhya pradesh', 'मध्य प्रदेश'), ('ap', 'andhra pradesh', 'ఆంధ్రప్రదేశ్'), ('pb', 'punjab', 'ਪੰਜਾਬ'), ('od', 'odisha', 'ଓଡ଼ିଶା'),
]
INDIA_ALIASES = [('orissa', 'odisha'), ('keralam', 'kerala')]          # S1 says Orissa, S2 says Keralam
FRANCE_REGIONS = ['hauts de france', 'nouvelle aquitaine', 'pays de la loire']
FRANCE_DEPARTMENTS = {   # public geography of the three observed regions; a département is admitted only if it occurs >= 1000 times as a whole segment
    'hauts de france': ['aisne', 'nord', 'oise', 'pas de calais', 'somme'],
    'nouvelle aquitaine': ['charente', 'charente maritime', 'correze', 'creuse', 'deux sevres', 'dordogne', 'gironde', 'haute vienne', 'landes',
                           'lot et garonne', 'pyrenees atlantiques', 'vienne'],
    'pays de la loire': ['loire atlantique', 'maine et loire', 'mayenne', 'sarthe', 'vendee'],
}
# (tier, abbreviation, expansion, rule). Rules: any | suffix (expand at the end of a segment or before a unit word or number, so "St Louis" stays) |
# suffix_multi (like suffix but never a whole segment: ``CT`` alone is the state Connecticut; evidence is then counted per segment, not per token).
# Admitted only if the token occurs >= 3000 times and is >= 4x more frequent per token in S2/S3 than in S1 (abbreviation_candidates.md).
CURATED_ABBREV = [
    ('US', 'st', 'street', 'suffix'), ('US', 'rd', 'road', 'suffix'), ('US', 'dr', 'drive', 'suffix'), ('US', 'ave', 'avenue', 'suffix'),
    ('US', 'ln', 'lane', 'suffix'), ('US', 'cir', 'circle', 'suffix'), ('US', 'pl', 'place', 'suffix'), ('US', 'blvd', 'boulevard', 'suffix'),
    ('US', 'trl', 'trail', 'suffix'), ('US', 'pkwy', 'parkway', 'suffix'), ('US', 'ter', 'terrace', 'suffix'), ('US', 'cv', 'cove', 'suffix'),
    ('US', 'ft', 'fort', 'any'),
    ('US', 'ct', 'court', 'suffix_multi'), ('US', 'hwy', 'highway', 'suffix_multi'), ('US', 'sq', 'square', 'suffix_multi'),
    ('FR', 'r', 'rue', 'any'), ('FR', 'av', 'avenue', 'any'), ('FR', 'ave', 'avenue', 'any'), ('FR', 'blvd', 'boulevard', 'any'),
    ('FR', 'imp', 'impasse', 'any'), ('FR', 'rte', 'route', 'any'), ('FR', 'ch', 'chemin', 'any'), ('FR', 'all', 'allee', 'any'),
    ('FR', 'st', 'saint', 'any'), ('FR', 'crs', 'cours', 'any'),
]
# Injected components (S2/S3 only). kind: placeholder_segment (a whole segment is dropped) | noise_token (token dropped)
# `na`, `none` and `nan` were considered and REJECTED by the evidence: S1 has as many whole-segment `na` (200) as S2 (369), so they are real segments.
# Kinds: placeholder_segment (whole segment dropped) | noise_token (token dropped) | noise_token_number (token + following number dropped, only if a
# number follows) | noise_segment_word (a segment containing the token is dropped) | noise_pattern (US ``po box n``).
# Admission for token/segment kinds: >= 5,000 occurrences in S2+S3 and a per-token S2/S3-to-S1 lift >= 20 in the unlabeled census; placeholder segments:
# >= 3,000 whole-segment occurrences and S2+S3 >= 100x S1. India entries were found by scanning the census for high-lift tokens (hn, b3, region) and
# by reviewing the full-data extraction sample (DIVREPORTINGCIRCLE); on true pairs they occur in the S1 address in 0-3% of cases (address_eval_pairs.py).
CURATED_NOISE = [('placeholder_segment', 'null', 'all'), ('placeholder_segment', 'n a', 'all'), ('placeholder_segment', 'divreportingcircle', 'India'),
                 ('noise_token', 'cdp', 'US'), ('noise_token', 'pmb', 'US'), ('noise_pattern', 'po box', 'US'),
                 ('noise_token_number', 'hn', 'India'), ('noise_token', 'b3', 'India'), ('noise_segment_word', 'region', 'India')]

KEY = r"trim(regexp_replace(lower(nfc_normalize(replace(replace(seg, chr(8204), ''), chr(8205), ''))), '[^\p{L}\p{M}\p{N}]+', ' ', 'g'))"


def write_tsv(name, header, rows):
    with (LEXICON_DIR / name).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t', lineterminator='\n', quoting=csv.QUOTE_NONE, escapechar=None)
        writer.writerow(header)
        writer.writerows(rows)


def segment_counts(con, country, forms):
    """Whole-segment occurrences of each form, by source, in the fitting corpus of the country."""
    result = {f: [0, 0, 0] for f in forms}
    lit = ','.join("'" + f.replace("'", "''") + "'" for f in forms)
    for source in (1, 2, 3):
        path = (INTERIM / f'{SPLIT[country]}_source{source}.parquet').as_posix()
        for key, n in con.execute(f"""SELECT k, count(*) FROM (SELECT {KEY} AS k FROM (SELECT unnest(string_split(business_address, ',')) AS seg
            FROM read_parquet('{path}') WHERE country = '{country}')) WHERE k IN ({lit}) GROUP BY k""").fetchall():
            result[key][source - 1] = n
    return result


def segment_evidence(con, abbr, expansion):
    """Per-segment evidence for a suffix_multi abbreviation (the token census is confounded by state codes such as CT)."""
    counts = []
    for source in (1, 2, 3):
        path = (INTERIM / f'train_source{source}.parquet').as_posix()
        rows, a, e = con.execute(f"""SELECT (SELECT count(*) FROM read_parquet('{path}') WHERE country = 'US'), sum((k LIKE '% {abbr}')::INT), sum((k LIKE '% {expansion}')::INT)
            FROM (SELECT {KEY} AS k FROM (SELECT unnest(string_split(business_address, ',')) AS seg FROM read_parquet('{path}') WHERE country = 'US'))""").fetchone()
        counts.append((rows, a, e))
    (r1, a1, e1), (r2, a2, e2), (r3, a3, e3) = counts
    lift = ((a2 + a3) / (r2 + r3)) / (max(a1, 1) / r1)
    evidence = (f"multi-token segments ending in '{abbr}', train US: S1 {a1:,} / S2+S3 {a2 + a3:,}; per-row rate lift {lift:.1f}x; a whole-segment '{abbr}' is never "
                f"expanded; full form '{expansion}': S1 {e1:,} / S2+S3 {e2 + e3:,}")
    return a1, a2 + a3, lift, evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    con = duckdb.connect()
    con.execute("SET memory_limit='4GB'")
    con.execute('SET threads=4')
    rows, excluded = [], []

    def add(country, form, canonical, kind, counts, minimum, corpus):
        assert unicodedata.normalize('NFC', form) == form, form
        total = sum(counts)
        if total < minimum:
            excluded.append((country, form, kind, total))
            return
        rows.append((country, form, canonical, kind, counts[0], counts[1], counts[2],
                     f'whole-segment occurrences in {corpus} S1/S2/S3: {counts[0]:,} / {counts[1]:,} / {counts[2]:,}'))

    # ---- US
    forms = list(US_STATES) + list(US_STATES.values())
    counts = segment_counts(con, 'US', forms)
    for code, name in US_STATES.items():
        add('US', code, name, 'code', counts[code], MIN_STATE_OBSERVATIONS, 'train')
        add('US', name, name, 'name', counts[name], MIN_STATE_OBSERVATIONS, 'train')
    # ---- India
    forms = [c for c, _n, _v in INDIA] + [n for _c, n, _v in INDIA] + [v for _c, _n, v in INDIA] + [a for a, _c in INDIA_ALIASES]
    counts = segment_counts(con, 'India', forms)
    for code, name, native in INDIA:
        add('India', code, name, 'code', counts[code], MIN_STATE_OBSERVATIONS, 'train')
        add('India', name, name, 'name', counts[name], MIN_STATE_OBSERVATIONS, 'train')
        add('India', native, name, 'native', counts[native], MIN_STATE_OBSERVATIONS, 'train')
    for alias, name in INDIA_ALIASES:
        add('India', alias, name, 'alias', counts[alias], MIN_STATE_OBSERVATIONS, 'train')
    # ---- France
    forms = FRANCE_REGIONS + [d for ds in FRANCE_DEPARTMENTS.values() for d in ds]
    counts = segment_counts(con, 'France', forms)
    for region in FRANCE_REGIONS:
        add('France', region, region, 'name', counts[region], MIN_DEPARTMENT_OBSERVATIONS, 'test (unlabeled)')
    for region, departments in FRANCE_DEPARTMENTS.items():
        for department in departments:
            add('France', department, region, 'department', counts[department], MIN_DEPARTMENT_OBSERVATIONS, 'test (unlabeled)')
    for country in ('US', 'India', 'France'):
        kinds = {}
        for r in rows:
            if r[0] == country:
                kinds[r[3]] = kinds.get(r[3], 0) + 1
        print(f'{country:7s} states.tsv rows by kind: {kinds}')
    print('excluded for lack of evidence:', [(c, f, k, n) for c, f, k, n in excluded])

    # ---- abbreviations (evidence from the token census)
    census = {}
    with CENSUS.open(encoding='utf-8') as stream:
        for r in csv.DictReader(stream):
            census[(r['country'], r['token'])] = (int(r['s1']), int(r['s23']), float(r['lift']))
    tier_country = {'US': 'US', 'FR': 'France', 'IN': 'India'}
    abbrev_rows = []
    for tier, abbr, expansion, rule in CURATED_ABBREV:
        if rule == 'suffix_multi':
            s1, s23, lift, evidence = segment_evidence(con, abbr, expansion)
            if s23 < 3000 or lift < 4:
                print(f'abbreviation excluded (no evidence): {tier} {abbr} -> {expansion}: {evidence}')
                continue
            abbrev_rows.append((tier, abbr, expansion, rule, s1, s23, f'{lift:.1f}', evidence))
            continue
        s1, s23, lift = census.get((tier_country[tier], abbr), (0, 0, 0.0))
        if s1 + s23 < 3000 or lift < 4:
            print(f'abbreviation excluded (no evidence): {tier} {abbr} -> {expansion}: S1 {s1} S2+S3 {s23} lift {lift}')
            continue
        abbrev_rows.append((tier, abbr, expansion, rule, s1, s23, f'{lift:.1f}', f'v1 token occurrences {tier_country[tier]}: S1 {s1:,} / S2+S3 {s23:,}; lift {lift:.1f}x'))
    # ---- noise
    noise_rows = []
    for kind, token, scope in CURATED_NOISE:
        if kind == 'placeholder_segment':
            counts = {}
            for source in (1, 2, 3):
                total = 0
                for country in ('US', 'India') if scope == 'all' else (scope,):
                    path = (INTERIM / f'train_source{source}.parquet').as_posix()
                    total += con.execute(f"""SELECT count(*) FROM (SELECT {KEY} AS k FROM (SELECT unnest(string_split(business_address, ',')) AS seg
                        FROM read_parquet('{path}') WHERE country = '{country}')) WHERE k = ?""", [token]).fetchone()[0]
                counts[source] = total
            where = 'US+India' if scope == 'all' else scope
            evidence = f'whole-segment occurrences in train {where} S1/S2/S3: {counts[1]:,} / {counts[2]:,} / {counts[3]:,}'
            if counts[2] + counts[3] < 3000 or counts[2] + counts[3] < 100 * max(counts[1], 1):
                print(f'noise excluded (no evidence): {kind} {token} {scope}: {evidence}')
                continue
        elif kind == 'noise_pattern':
            po, box = census.get(('US', 'po'), (0, 0, 0.0)), census.get(('US', 'box'), (0, 0, 0.0))
            evidence = f'v1 token occurrences US: po S1 {po[0]:,} / S2+S3 {po[1]:,}; box S1 {box[0]:,} / S2+S3 {box[1]:,} (an injected PO BOX n component)'
        else:
            s1, s23, lift = census.get((scope, token), (0, 0, 0.0))
            evidence = f'v1 token occurrences {scope}: S1 {s1:,} / S2+S3 {s23:,}; lift {lift:.1f}x'
            if s23 < 5000 or lift < 20:
                print(f'noise excluded (no evidence): {kind} {token} {scope}: {evidence}')
                continue
        noise_rows.append((kind, token, scope, evidence))
        print('noise', kind, token, evidence)
    if not args.write:
        print('\nreport only: nothing written (use --write)')
        return 0
    write_tsv('states.tsv', ['country', 'form', 'canonical', 'kind', 'observed_s1', 'observed_s2', 'observed_s3', 'evidence'], rows)
    write_tsv('address_abbrev.tsv', ['tier', 'abbr', 'expansion', 'rule', 'observed_s1', 'observed_s23', 'lift', 'evidence'], abbrev_rows)
    write_tsv('address_noise.tsv', ['kind', 'token', 'scope', 'evidence'], noise_rows)
    print('written to', LEXICON_DIR)
    return 0


if __name__ == '__main__':
    sys.exit(main())
