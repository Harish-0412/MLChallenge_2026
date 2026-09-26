"""Render measured JSON diagnostics into the team's Markdown audit report."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/eda'


def table(headers, rows):
    def cell(value):
        return str(value).replace('|','\\|').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
        ['| '+' | '.join(cell(v) for v in row)+' |' for row in rows])


def pct(n,d):
    return f'{100*n/d:.2f}%' if d else 'N/A'


def main():
    r=json.loads((OUT/'full_audit.json').read_text(encoding='utf-8'))
    t=json.loads((OUT/'text_quality_details.json').read_text(encoding='utf-8'))
    v=json.loads((OUT/'verification.json').read_text(encoding='utf-8'))
    assert r['complete'] and v['complete']
    profiles=[(file,row) for file,rows in r['profiles'].items() for row in rows]
    pos=r['positive_pairs']
    total_links=sum(x['links'] for x in pos)
    exact_links=sum(x['exact_name_or_address_retrievable'] for x in pos)
    total_entities=sum(x['s1_entities'] for x in r['exact_key_oracle'])
    oracle=sum(x['s1_entities']*x['macro_f05_oracle_ceiling'] for x in r['exact_key_oracle'])/total_entities
    lines=[
        '# Measured EDA findings: Amazon ML Challenge 2026',
        '',
        f"Generated from full audit started at `{r['created_utc']}`. Audit runtime: {r['elapsed_seconds']:.2f} seconds, excluding the separate script census and verification.",
        '',
        '## Scope and evidence',
        '',
        'Every row in all six source TSVs and the complete training ground truth was parsed and queried. Normalized equality, missingness, label checks, script counts and overlap results below are full-data measurements. Fuzzy similarity distributions use a separately identified deterministic positive-pair sample. No retrieval index or classifier has been trained or validated.',
        '',
        'Artifacts: [full audit](full_audit.json), [text details](text_quality_details.json), [verification](verification.json), [source-country CSV](file_country_profile.csv), [positive-link CSV](positive_pair_profile.csv).',
        '',
        '## Decision-changing findings',
        '',
        f"- Exact country + normalized name OR nonempty normalized address equality retrieves only **{pct(exact_links,total_links)}** of true training links. Its perfect-classifier macro F0.5 ceiling is **{oracle:.6f}**. Fuzzy and cross-script retrieval are necessary experiments.",
        '- Nine Indian script families occur in target names. Devanagari-only transliteration is insufficient.',
        '- Some strings contain zero-width non-joiners and some addresses contain control characters associated with encoding artifacts. These need flags and tested auxiliary cleaning.',
        '- Placeholder-like business names exist, including literal `NA`; retain their text and add a flag instead of parser-driven null conversion.',
        '- Names alone collide heavily. The current name+address+country key is unique in training Source 1, but two French test Source 1 IDs share the same normalized tuple. Keep both IDs.',
        '- All labeled positive links have valid target IDs and matching countries; no labeled target is assigned to two Source 1 IDs.',
        '- Raw input SHA-256 values are unchanged after processing. Every source record remains in its derived Parquet file.',
        '',
        '## 1. Row counts, country and missingness',
        '',
        table(['File','Country','Rows','Blank addresses','Blank address %'],[
            [file,row['country'],f"{row['rows']:,}",f"{row['missing_address']:,}",pct(row['missing_address'],row['rows'])] for file,row in profiles]),
        '',
        f"Total source records: **{sum(row['rows'] for _,row in profiles):,}**. TSV bytes including labels: **{sum(x['bytes'] for x in r['files']):,}**.",
        '',
        'Blank name fields and blank country fields are absent. That is a structural statement; the placeholder-like names below still need semantic missingness flags.',
        '',
        '## 2. Text defects and format characters',
        '',
        table(['File','Rows with control characters','Rows with format characters','Names with combining marks','Placeholder-like names'],[
            [file,f"{sum(x['control_character_rows'] for x in rows):,}",f"{sum(x['format_character_rows'] for x in rows):,}",
             f"{sum(x['name_contains_combining_marks'] for x in rows):,}",f"{sum(x['name_placeholder_like'] for x in rows):,}"]
            for file,rows in r['profiles'].items()]),
        '',
        'Each control/format count is the number of records whose concatenated name/address contains at least one such character, not the number of characters. Unicode categories `Cc` and `Cf` differ from combining marks (`M`): marks are often essential script content. Bounded examples in `text_quality_details.json` include U+001A, U+0080/U+0093-like encoding artifacts, and U+200C ZERO WIDTH NON-JOINER. Example-character frequencies are samples, not full counts.',
        '',
        f"Replacement-character rows (U+FFFD): {sum(x['replacement_character_rows'] for _,x in profiles):,}. A zero count would not rule out mojibake: the observed artifacts can be valid Unicode code points with incorrect encoding history.",
        '',
        'Keep original strings. The baseline key converts punctuation/control/format characters into token boundaries; a later joiner-aware or encoding-repair view needs its own version and evaluation. Do not remove all non-ASCII characters or all diacritics.',
        '',
        '## 3. Indian script census in business names',
        '',
    ]
    scripts=[('Devanagari','devanagari'),('Bengali','bengali'),('Gujarati','gujarati'),('Gurmukhi','gurmukhi'),('Odia / Unicode Oriya','oriya'),('Tamil','tamil'),('Telugu','telugu'),('Kannada','kannada'),('Malayalam','malayalam')]
    files=['train_source2','train_source3','test_source2','test_source3']
    lines += [table(['Script']+files,[[label]+[f"{sum(row[key+'_name'] for row in t['script_census'][file]):,}" for file in files] for label,key in scripts]),'',
        'Counts mean at least one character belonging to that script in the field. Mixed-script records can contribute to several columns; do not assume these categories are mutually exclusive. Script does not uniquely identify spoken language. Full per-country name/address counts, including checks for Arabic, Cyrillic and Han, are in the JSON.',
        '',
        '## 4. Repeated names and identical payloads',
        '',
        'Normalization here is `nfc_lower_lmn_v1`: NFC, lowercase, preserve Unicode letters/marks/numbers, replace other runs with spaces. It does not transliterate, expand ampersands or strip legal suffixes. Counts are grouped by country and use exact string grouping, not a 64-bit digest approximation.',
        '',
        table(['File','Extra rows sharing a name key','Extra rows sharing name+address key','Largest same-name group','Exact raw-payload extra rows'],[
            [file,f"{sum(x['repeat_rows_after_first'] for x in item['name']):,}",f"{sum(x['repeat_rows_after_first'] for x in item['name_and_address']):,}",
             max(x['largest_group'] for x in item['name']),f"{item['raw_payload_duplicate_rows']:,}"] for file,item in r['collisions'].items()]),
        '',
        'Duplicate-looking S2/S3 payloads remain separate records because the task predicts record IDs, including multiple variants. Do not deduplicate these rows. The older exploratory script used a different ampersand rule and could remove combining marks, so its normalized-name repetition/token counts are superseded by this report.',
        '',
        'A concrete test-reference ambiguity: `S1-202327133` and `S1-628518958` are both `Lille Club SAS`, with addresses differing only in spacing/casing around `72-74 RUE Royale, Maison des associations, Lille, Hauts-de-France`. The conservative key collapses these differences. This does not prove the official identities are duplicates: test labels are unknown. Keep both reference IDs, preserve raw text, and record the ambiguity rather than merging them.',
        '',
        '## 5. Train/test overlap',
        '',
        table(['Source','Shared IDs','Test rows with identical raw train payload','Test rows with equal normalized train payload'],[
            [f"S{x['source']}",x['same_id_overlap'],x['test_records_with_exact_train_payload'],x['test_records_with_equal_normalized_train_payload']] for x in r['cross_split']]),
        '',
        'Payload means name + address + country, excluding ID. Counts are test-record counts with at least one train counterpart, not join-pair counts. Some S2/S3 normalized payloads overlap while all IDs and raw payloads are disjoint. This can arise from cosmetic variants or ambiguous common names; it is not authorization to copy training labels onto test entities. No exact S1 payload overlap was found, but semantic/near-duplicate overlap has not been exhaustively ruled out.',
        '',
        '## 6. Ground-truth integrity and cardinality',
        '',
        table(['Check','Measured value'],[[key,f'{value:,}'] for key,value in r['truth_integrity'].items()]),
        '',
        'All positive-pair joins found their targets; country mismatches are zero. Source 1 truth coverage is exact. Target ownership uniqueness is a property of supplied labels, to be tested as a later postprocessing constraint.',
        '',
        table(['Country','S1 entities','Singletons','Singleton %'],[
            [x['country'],f"{x['s1_entities']:,}",f"{x['singletons']:,}",pct(x['singletons'],x['s1_entities'])] for x in r['exact_key_oracle']]),
        '',
        'The full match-count distribution is in [match_count_distribution.csv](match_count_distribution.csv). Keep singleton S1 rows even when expanding labels into positive pairs.',
        '',
        '## 7. Full positive-pair analysis',
        '',
        table(['Country','Target source','True links','Equal name key','Equal address key','Either exact key','Missing target address'],[
            [x['country'],f"S{x['target_source']}",f"{x['links']:,}",pct(x['name_key_equal'],x['links']),pct(x['address_key_equal'],x['links']),
             pct(x['exact_name_or_address_retrievable'],x['links']),pct(x['missing_target_addresses'],x['links'])] for x in pos]),
        '',
        'Address equality requires nonempty normalized address. The exact-key union is measured on true links only; its false-candidate volume and actual precision have not been measured. It is not a final blocking benchmark.',
        '',
        table(['Country','Target source','Both addresses have ASCII numeric tokens','No numeric token shared','Conflict fraction within numeric pairs'],[
            [x['country'],f"S{x['target_source']}",f"{x['both_have_numeric_token']:,}",f"{x['disjoint_numeric_tokens']:,}",
             pct(x['disjoint_numeric_tokens'],x['both_have_numeric_token'])] for x in pos]),
        '',
        'Numeric tokens here are simple `[0-9]+` substrings, not verified house or postal numbers. True matches can share none, so an absolute shared-number requirement would lose those links. Missing addresses are excluded from the numeric-pair denominator.',
        '',
        '## 8. Exact-key oracle ceiling',
        '',
        table(['Country','Oracle macro F0.5','All links retrieved, including singleton successes','Complete coverage among non-singletons'],[
            [x['country'],f"{x['macro_f05_oracle_ceiling']:.6f}",f"{x['entities_all_links_retrieved_including_singletons']:,}",
             pct(x['entities_all_links_retrieved_including_singletons']-x['singletons'],x['s1_entities']-x['singletons'])] for x in r['exact_key_oracle']]),
        '',
        f'Weighted across all training S1 entities, the oracle is **{oracle:.6f}**. It selects every available true match and rejects every false candidate. Practical exact-key caps can only lower that ceiling. A union of fuzzy/rare-token/script-aware channels is the next retrieval experiment.',
        '',
        '## 9. Sampled positive fuzzy similarity',
        '',
        'Selection uses `hash(source1_entity_id,target_id) % 200 == 0` in pinned DuckDB 1.4.3. This is a deterministic approximately 0.5% pair sample, not a random split of S1 entities, and not a held-out validation set. Similarities use RapidFuzz `ratio` on the conservative keys with its 0-100 scale.',
        '',
        table(['Country','Target source','Sample pairs','Name ratio p10 / median / p90','Name ratio below 50'],[
            [x['country'],source,f"{x['sample_pairs']:,}",' / '.join(f'{q:.2f}' for q in x['name_ratio_p10_p50_p90']),pct(x['name_ratio_below_50'],x['sample_pairs'])]
            for source,item in r['pair_sample'].items() for x in item['summary']]),
        '',
        'These are all positive pairs. Low similarities demonstrate why a single name threshold can miss true links, especially cross-script Indian records. They cannot establish classification accuracy or choose a safe threshold without hard-negative distributions.',
        '',
        '## 10. Output verification and next steps',
        '',
        '- All seven original-file SHA-256 values were rechecked and are unchanged.',
        '- All six Parquet files match their database table row counts and aggregate row-content hashes.',
        f"- Python and SQL normalizers agree on {sum(x['records_checked'] for x in v['normalization_sample_checks']):,} sampled records (both names and addresses).",
        '- Focused regression tests cover Unicode marks, accent handling, number preservation, normalization parity/idempotence, strict TSV parsing and F0.5 edge cases.',
        '',
        'Verification uses full row counts/fingerprints and a normalization sample; it is not a claim of independent manual inspection of 24 million records. Sources were never edited. Basic normalization was applied to all records, while richer cleaning, frozen splits, actual candidate generation, hard negatives and training remain separate work packages.',
        '',
        'Proceed using the [two-person plan](../../docs/TEAM_PRETRAINING_PLAN.md). A owns tested multilingual/encoding/address views and storage; B owns frozen splits, metric, retrieval benchmarks and pair EDA. Do not begin model training until the stated handoff criteria are met.',
        ''
    ]
    (OUT/'EDA_FINDINGS.md').write_text('\n'.join(lines),encoding='utf-8')
    print(f'Wrote {OUT/"EDA_FINDINGS.md"}')


if __name__=='__main__':
    main()
