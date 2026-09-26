"""Phase 3: write the name lexicons from a curated definition plus measured counts.

    python scripts/build_name_lexicons.py            # report only: shows coverage gaps, writes nothing
    python scripts/build_name_lexicons.py --write    # writes src/cleaning/lexicon_data/{legal_forms,name_noise_tokens,generic_tokens,placeholders,country_tiers}.tsv

The *choice* of legal-form and noise tokens is curated below and justified by the census in
reports/cleaning/name_token_census/ (run scripts/name_token_census.py first). Counts written into the lexicons are
measured here from the v1 keys so every entry carries its evidence. Only unlabeled statistics are used.

Generic-token document frequencies are fitted on TRAIN Source 1 for countries that occur in train (US, India) and on
unlabeled TEST Source 1 for countries that do not (France), as agreed in reports/cleaning/contract_feat_v2_0.md.
"""
import argparse
import csv
import sys
import unicodedata
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
INTERIM = ROOT / 'data' / 'interim'
LEXICON_DIR = ROOT / 'src' / 'cleaning' / 'lexicon_data'
CENSUS = ROOT / 'reports' / 'cleaning' / 'name_token_census'

# (tier, token, code, rank). rank orders the codes inside `legal_form` (PVT before LTD, so "Private Limited" == "Pvt Ltd" == PVT+LTD).
CURATED_LEGAL = [
    ('generic', 'llc', 'LLC', 10), ('generic', 'llp', 'LLP', 11), ('generic', 'lp', 'LP', 12),
    ('generic', 'limited', 'LTD', 20), ('generic', 'ltd', 'LTD', 20),
    ('generic', 'inc', 'INC', 30), ('generic', 'incorporated', 'INC', 30),
    ('generic', 'corp', 'CORP', 40), ('generic', 'corporation', 'CORP', 40),
    ('generic', 'co', 'CO', 50), ('generic', 'company', 'CO', 50),
    ('US', 'pllc', 'PLLC', 13), ('US', 'pc', 'PC', 14), ('US', 'pa', 'PA', 15),
    ('IN', 'private', 'PVT', 1), ('IN', 'pvt', 'PVT', 1),
    ('FR', 'sarl', 'SARL', 10), ('FR', 'sas', 'SAS', 11), ('FR', 'sasu', 'SASU', 12), ('FR', 'eurl', 'EURL', 13),
    ('FR', 'sa', 'SA', 14), ('FR', 'sci', 'SCI', 15), ('FR', 'ei', 'EI', 16), ('FR', 'snc', 'SNC', 17), ('FR', 'cie', 'CIE', 51),
]
# Native-script legal words (tier 'native', active for every country: a script is unambiguous). Curated from
# reports/cleaning/native_legal_candidates.md (unlabeled, train S2+S3 India): Limited ends 69-83% of native-script names, Private is
# second-to-last in 57-72%, LLP ends ~5.5%; Devanagari/Gurmukhi/Gujarati also carry the abbreviation pair "Pvt." + "Ltd." in the same 13.0% of
# names. (script, token, code, rank); rank equals the Latin code's rank. Every token is asserted below to occur in >= 5% of its script's names.
CURATED_NATIVE = [
    ('Devanagari', 'लिमिटेड', 'LTD', 20), ('Devanagari', 'लि', 'LTD', 20), ('Devanagari', 'प्राइवेट', 'PVT', 1),
    ('Devanagari', 'प्रा', 'PVT', 1), ('Devanagari', 'एलएलपी', 'LLP', 11),
    ('Bengali', 'লিমিটেড', 'LTD', 20), ('Bengali', 'প্রাইভেট', 'PVT', 1), ('Bengali', 'এলএলপি', 'LLP', 11),
    ('Gurmukhi', 'ਲਿਮਟਿਡ', 'LTD', 20), ('Gurmukhi', 'ਲਿ', 'LTD', 20), ('Gurmukhi', 'ਪ੍ਰਾਈਵੇਟ', 'PVT', 1),
    ('Gurmukhi', 'ਪ੍ਰਾ', 'PVT', 1), ('Gurmukhi', 'ਐਲਐਲਪੀ', 'LLP', 11),
    ('Gujarati', 'લિમિટેડ', 'LTD', 20), ('Gujarati', 'લિ', 'LTD', 20), ('Gujarati', 'પ્રાઇવેટ', 'PVT', 1),
    ('Gujarati', 'પ્રા', 'PVT', 1), ('Gujarati', 'એલએલપી', 'LLP', 11),
    ('Oriya', 'ଲିମିଟେଡ୍', 'LTD', 20), ('Oriya', 'ପ୍ରାଇଭେଟ୍', 'PVT', 1), ('Oriya', 'ଏଲ୍ଏଲ୍ପି', 'LLP', 11),
    ('Tamil', 'லிமிடெட்', 'LTD', 20), ('Tamil', 'பிரைவேட்', 'PVT', 1), ('Tamil', 'எல்எல்பி', 'LLP', 11),
    ('Telugu', 'లిమిటెడ్', 'LTD', 20), ('Telugu', 'ప్రైవేట్', 'PVT', 1), ('Telugu', 'ఎల్ఎల్పీ', 'LLP', 11),
    ('Kannada', 'ಲಿಮಿಟೆಡ್', 'LTD', 20), ('Kannada', 'ಪ್ರೈವೇಟ್', 'PVT', 1), ('Kannada', 'ಎಲ್ಎಲ್ಪಿ', 'LLP', 11),
    ('Malayalam', 'ലിമിറ്റഡ്', 'LTD', 20), ('Malayalam', 'പ്രൈവറ്റ്', 'PVT', 1), ('Malayalam', 'എൽഎൽപി', 'LLP', 11),
]
COUNTRY_TIERS = [('US', 'US'), ('India', 'IN'), ('France', 'FR')]
PLACEHOLDERS = ['na', 'n/a', 'null', 'none', 'nan', 'unknown', '-']   # identical to scripts/audit_dataset.py
# kind, token, note. Evidence counts are measured below.
NOISE = [('leading', 'the'), ('leading', 'dr'), ('leading', 'mr'), ('leading', 'sri'), ('leading', 'shri'), ('leading', 'smt'),
         ('leading_pattern', 'm/s'), ('connector', 'and')]
NOISE_LIFT_MIN, NOISE_COUNT_MIN = 5.0, 3000   # appended-noise: last-position share in S2/S3 >= 5x the S1 share, >= 3000 occurrences
GENERIC_SHARE = 0.0025          # a token in at least 0.25% of Source 1 names of the country is "generic" (common, weakly discriminating)
TABLES = {(s, sp): INTERIM / f'{sp}_source{s}.parquet' for s in (1, 2, 3) for sp in ('train', 'test')}


def write_tsv(name, header, rows):
    path = LEXICON_DIR / name
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t', lineterminator='\n', quoting=csv.QUOTE_NONE, escapechar=None)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def token_counts(con, tokens, country=None):
    """Names containing the token, by source (S1/S2/S3), optionally for one country."""
    out = {}
    for token in tokens:
        counts = [0, 0, 0]
        for (source, _split), path in TABLES.items():
            where = f"AND country='{country}'" if country else ''
            n = con.execute(f"SELECT count(*) FROM read_parquet('{path.as_posix()}') WHERE list_contains(string_split(name_key,' '), ?) {where}", [token]).fetchone()[0]
            counts[source - 1] += n
        out[token] = counts
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    con = duckdb.connect()
    con.execute("SET memory_limit='4GB'")
    con.execute('SET threads=4')

    tier_country = {'US': 'US', 'IN': 'India', 'FR': 'France'}
    legal_rows = []
    for tier, token, code, rank in CURATED_LEGAL:
        n = token_counts(con, [token], tier_country.get(tier))[token]
        scope = f'names of {tier_country[tier]}' if tier in tier_country else 'names of all countries'
        legal_rows.append((tier, token, code, rank, sum(n), f'{scope} containing the token: S1 {n[0]:,} / S2 {n[1]:,} / S3 {n[2]:,} (v1 tokens, all splits)'))
        print(f'legal {tier:8s} {token:13s} {code:5s} {n}')

    native_key = r"trim(regexp_replace(lower(nfc_normalize(replace(replace(business_name, chr(8204), ''), chr(8205), ''))), '[^\p{L}\p{M}\p{N}]+', ' ', 'g'))"
    india_native = ' UNION ALL '.join(f"SELECT {native_key} AS k, business_name FROM read_parquet('{TABLES[(s, 'train')].as_posix()}') WHERE country='India'" for s in (2, 3))
    for script, token, code, rank in CURATED_NATIVE:
        assert unicodedata.normalize('NFC', token) == token, (script, token)
        n = con.execute(f"SELECT count(*) FROM ({india_native}) WHERE regexp_matches(business_name, '\\p{{{script}}}') AND list_contains(string_split(k, ' '), ?)", [token]).fetchone()[0]
        names = con.execute(f"SELECT count(*) FROM ({india_native}) WHERE regexp_matches(business_name, '\\p{{{script}}}')").fetchone()[0]
        assert n / names >= 0.05, f'curated native token {token!r} ({script}) occurs in only {n}/{names} names: typo?'
        legal_rows.append(('native', token, code, rank, n, f'{script} names in train S2+S3 India containing the token: {n:,} of {names:,} ({100 * n / names:.1f}%); curated from native_legal_candidates.md'))
        print(f'native {script:11s} {token:16s} {code:4s} {n:>8,} ({100 * n / names:.1f}% of {script} names)')

    noise_rows = []
    for kind, token in NOISE:
        if kind == 'leading_pattern':
            n = [0, 0, 0]
            for (source, split), path in TABLES.items():
                if split == 'train':
                    n[source - 1] += con.execute(f"SELECT count(*) FROM read_parquet('{path.as_posix()}') WHERE regexp_matches(business_name, '^\\s*[Mm]\\s*/\\s*[Ss]([^A-Za-z]|$)')").fetchone()[0]
            note = f'train names starting with M/s (raw pattern): S1 {n[0]:,} / S2 {n[1]:,} / S3 {n[2]:,}'
        else:
            n = [0, 0, 0]
            for (source, split), path in TABLES.items():
                if split == 'train':
                    cond = "split_part(name_key,' ',1)=?" if kind == 'leading' else "list_contains(string_split(name_key,' '), ?)"
                    n[source - 1] += con.execute(f"SELECT count(*) FROM read_parquet('{path.as_posix()}') WHERE {cond}", [token]).fetchone()[0]
            where = 'as first token' if kind == 'leading' else 'as a token'
            note = f'train names with `{token}` {where}: S1 {n[0]:,} / S2 {n[1]:,} / S3 {n[2]:,}'
        noise_rows.append((kind, token, sum(n), note))
        print(f'noise {kind:15s} {token:6s} {n}')

    # coverage gaps: frequent edge tokens that are not in the legal lexicon (for review)
    lex_tokens = {t for _tier, t, _c, _r in CURATED_LEGAL}
    census = CENSUS / 'first_last_tokens.csv'
    if census.exists():
        print('\nfrequent first/last tokens NOT in the legal lexicon (review for missing legal forms):')
        rows = con.execute(f"""SELECT country, position, token, sum(count) AS n FROM read_csv('{census.as_posix()}') WHERE length(token)>1
            GROUP BY country, position, token ORDER BY country, position, n DESC""").fetchall()
        shown = {}
        for country, position, token, n in rows:
            if token in lex_tokens or not token.isascii():
                continue
            key = (country, position)
            shown.setdefault(key, [])
            if len(shown[key]) < 25:
                shown[key].append(f'{token}:{n:,}')
        for key, items in sorted(shown.items()):
            print(f'  {key[0]:7s} {key[1]:5s} ' + ', '.join(items))
    else:
        print('\n(no census found; run scripts/name_token_census.py for the coverage review)')

    # generic tokens
    generic_rows = []
    fl_path = CENSUS / 'first_last_tokens.csv'
    train_countries = {r[0] for r in con.execute(f"SELECT DISTINCT country FROM read_csv('{fl_path.as_posix()}') WHERE split='train'").fetchall()} if fl_path.exists() else set()
    df_path = CENSUS / 's1_document_freq.csv'
    if df_path.exists():
        legal_all = lex_tokens | {t for _k, t, *_ in noise_rows}
        for country, _tier in COUNTRY_TIERS:
            split = 'train' if country in train_countries else 'test'
            rows = con.execute(f"""SELECT token, docs, rows, share FROM read_csv('{df_path.as_posix()}')
                WHERE split=? AND country=? AND share>=? AND length(token)>=2 ORDER BY docs DESC, token""", [split, country, GENERIC_SHARE]).fetchall()
            kept = [r for r in rows if r[0] not in legal_all and not r[0].isdigit()]
            corpus = f'{split} Source 1' + ('' if split == 'train' else ' (unlabeled test text; no French training data exists)')
            generic_rows += [(country, t, d, n, f'{s:.5f}', corpus) for t, d, n, s in kept]
            print(f'generic tokens {country:7s} {len(kept):4d} tokens with share >= {GENERIC_SHARE:.2%} ({corpus})')
    else:
        print('(no document-frequency table; generic_tokens.tsv not written)')

    # appended-noise words (experimental view): last-position lift of S2/S3 over S1, same fitting-corpus rule as the generic tokens
    noise_word_rows = []
    if census.exists():
        for country, tier_name in COUNTRY_TIERS:
            split = 'train' if country in train_countries else 'test'
            skip = {t for tier, t, *_ in CURATED_LEGAL if tier in ('generic', tier_name)} | {'com'} | {t for _kind, t in NOISE}   # already handled elsewhere
            rows = con.execute(f"""WITH t AS (SELECT source, token, sum(count) AS n FROM read_csv('{census.as_posix()}')
                    WHERE country=? AND split=? AND position='last' GROUP BY source, token),
                r AS (SELECT source, max(rows) AS rows FROM read_csv('{census.as_posix()}') WHERE country=? AND split=? GROUP BY source)
                SELECT b.token, coalesce(a.n,0) AS s1, b.n AS s23, coalesce(a.n,0)*1.0/(SELECT rows FROM r WHERE source='S1') AS s1_share,
                    b.n*1.0/((SELECT rows FROM r WHERE source='S2')+(SELECT rows FROM r WHERE source='S3')) AS s23_share
                FROM (SELECT token, sum(n) AS n FROM t WHERE source<>'S1' GROUP BY token) b
                LEFT JOIN (SELECT token, n FROM t WHERE source='S1') a USING (token)
                WHERE b.n>=? ORDER BY b.n DESC""", [country, split, country, split, NOISE_COUNT_MIN]).fetchall()
            for token, s1, s23, s1_share, s23_share in rows:
                lift = s23_share / max(s1_share, 1e-9)
                if lift >= NOISE_LIFT_MIN and token.isascii() and len(token) >= 3 and token not in skip:
                    noise_word_rows.append((country, token, f'{lift:.1f}', f'{s1_share:.6f}', f'{s23_share:.6f}', f'{split} text'))
            print(f'appended-noise tokens {country:7s} {sum(1 for r in noise_word_rows if r[0] == country):3d} ({split} text)')

    if not args.write:
        print('\nreport only: nothing written (use --write)')
        return 0
    write_tsv('legal_forms.tsv', ['tier', 'token', 'code', 'rank', 'observed_count', 'evidence'], legal_rows)
    write_tsv('name_noise_tokens.tsv', ['kind', 'token', 'observed_count', 'evidence'], noise_rows)
    write_tsv('placeholders.tsv', ['token', 'evidence'],
              [(t, 'same list as scripts/audit_dataset.py profile(); 24 training S2+S3 names match and all 24 are true links') for t in PLACEHOLDERS])
    write_tsv('country_tiers.tsv', ['country', 'tier'], COUNTRY_TIERS)
    if generic_rows:
        write_tsv('generic_tokens.tsv', ['country', 'token', 'docs', 'rows', 'share', 'corpus'], generic_rows)
    if noise_word_rows:
        write_tsv('appended_noise.tsv', ['country', 'token', 'lift', 's1_share', 's23_share', 'corpus'], noise_word_rows)
    print('written to', LEXICON_DIR)
    return 0


if __name__ == '__main__':
    sys.exit(main())
