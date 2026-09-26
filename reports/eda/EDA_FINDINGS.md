# Measured EDA findings: Amazon ML Challenge 2026

Generated from full audit started at `2026-09-25T15:44:41.733383+00:00`. Audit runtime: 232.81 seconds, excluding the separate script census and verification.

## Scope and evidence

Every row in all six source TSVs and the complete training ground truth was parsed and queried. Normalized equality, missingness, label checks, script counts and overlap results below are full-data measurements. Fuzzy similarity distributions use a separately identified deterministic positive-pair sample. No retrieval index or classifier has been trained or validated.

Artifacts: [full audit](full_audit.json), [text details](text_quality_details.json), [verification](verification.json), [source-country CSV](file_country_profile.csv), [positive-link CSV](positive_pair_profile.csv).

## Decision-changing findings

- Exact country + normalized name OR nonempty normalized address equality retrieves only **28.80%** of true training links. Its perfect-classifier macro F0.5 ceiling is **0.518766**. Fuzzy and cross-script retrieval are necessary experiments.
- Nine Indian script families occur in target names. Devanagari-only transliteration is insufficient.
- Some strings contain zero-width non-joiners and some addresses contain control characters associated with encoding artifacts. These need flags and tested auxiliary cleaning.
- Placeholder-like business names exist, including literal `NA`; retain their text and add a flag instead of parser-driven null conversion.
- Names alone collide heavily. The current name+address+country key is unique in training Source 1, but two French test Source 1 IDs share the same normalized tuple. Keep both IDs.
- All labeled positive links have valid target IDs and matching countries; no labeled target is assigned to two Source 1 IDs.
- Raw input SHA-256 values are unchanged after processing. Every source record remains in its derived Parquet file.

## 1. Row counts, country and missingness

| File | Country | Rows | Blank addresses | Blank address % |
| --- | --- | --- | --- | --- |
| train_source1 | India | 883,188 | 0 | 0.00% |
| train_source1 | US | 1,323,633 | 0 | 0.00% |
| train_source2 | India | 2,017,799 | 57,846 | 2.87% |
| train_source2 | US | 3,016,817 | 111,121 | 3.68% |
| train_source3 | India | 2,115,547 | 64,948 | 3.07% |
| train_source3 | US | 3,170,056 | 110,968 | 3.50% |
| test_source1 | France | 259,452 | 0 | 0.00% |
| test_source1 | India | 809,986 | 0 | 0.00% |
| test_source1 | US | 663,106 | 0 | 0.00% |
| test_source2 | France | 703,378 | 21,537 | 3.06% |
| test_source2 | India | 2,312,565 | 52,764 | 2.28% |
| test_source2 | US | 1,871,330 | 55,107 | 2.94% |
| test_source3 | France | 731,615 | 21,541 | 2.94% |
| test_source3 | India | 2,405,000 | 59,240 | 2.46% |
| test_source3 | US | 1,945,701 | 55,317 | 2.84% |

Total source records: **24,229,173**. TSV bytes including labels: **2,520,573,701**.

Blank name fields and blank country fields are absent. That is a structural statement; the placeholder-like names below still need semantic missingness flags.

## 2. Text defects and format characters

| File | Rows with control characters | Rows with format characters | Names with combining marks | Placeholder-like names |
| --- | --- | --- | --- | --- |
| train_source1 | 605 | 0 | 0 | 0 |
| train_source2 | 1,232 | 25,643 | 474,128 | 6 |
| train_source3 | 1,072 | 14,514 | 278,095 | 18 |
| test_source1 | 529 | 0 | 0 | 0 |
| test_source2 | 1,365 | 31,104 | 546,373 | 49 |
| test_source3 | 1,180 | 17,468 | 320,182 | 61 |

Each control/format count is the number of records whose concatenated name/address contains at least one such character, not the number of characters. Unicode categories `Cc` and `Cf` differ from combining marks (`M`): marks are often essential script content. Bounded examples in `text_quality_details.json` include U+001A, U+0080/U+0093-like encoding artifacts, and U+200C ZERO WIDTH NON-JOINER. Example-character frequencies are samples, not full counts.

Replacement-character rows (U+FFFD): 0. A zero count would not rule out mojibake: the observed artifacts can be valid Unicode code points with incorrect encoding history.

Keep original strings. The baseline key converts punctuation/control/format characters into token boundaries; a later joiner-aware or encoding-repair view needs its own version and evaluation. Do not remove all non-ASCII characters or all diacritics.

## 3. Indian script census in business names

| Script | train_source2 | train_source3 | test_source2 | test_source3 |
| --- | --- | --- | --- | --- |
| Devanagari | 269,424 | 158,003 | 309,103 | 181,068 |
| Bengali | 30,723 | 18,144 | 35,546 | 20,872 |
| Gujarati | 30,929 | 18,020 | 35,321 | 20,570 |
| Gurmukhi | 6,688 | 4,106 | 7,903 | 4,634 |
| Odia / Unicode Oriya | 7,493 | 4,317 | 8,670 | 5,062 |
| Tamil | 33,781 | 19,790 | 38,953 | 22,808 |
| Telugu | 39,323 | 23,033 | 45,171 | 26,698 |
| Kannada | 37,211 | 21,995 | 43,906 | 25,832 |
| Malayalam | 18,773 | 11,116 | 22,033 | 13,095 |

Counts mean at least one character belonging to that script in the field. Mixed-script records can contribute to several columns; do not assume these categories are mutually exclusive. Script does not uniquely identify spoken language. Full per-country name/address counts, including checks for Arabic, Cyrillic and Han, are in the JSON.

## 4. Repeated names and identical payloads

Normalization here is `nfc_lower_lmn_v1`: NFC, lowercase, preserve Unicode letters/marks/numbers, replace other runs with spaces. It does not transliterate, expand ampersands or strip legal suffixes. Counts are grouped by country and use exact string grouping, not a 64-bit digest approximation.

| File | Extra rows sharing a name key | Extra rows sharing name+address key | Largest same-name group | Exact raw-payload extra rows |
| --- | --- | --- | --- | --- |
| train_source1 | 685,397 | 0 | 253 | 0 |
| train_source2 | 1,001,326 | 67,708 | 526 | 25,873 |
| train_source3 | 995,799 | 50,425 | 521 | 18,860 |
| test_source1 | 503,920 | 1 | 205 | 0 |
| test_source2 | 870,930 | 56,112 | 300 | 22,641 |
| test_source3 | 857,334 | 41,790 | 352 | 16,293 |

Duplicate-looking S2/S3 payloads remain separate records because the task predicts record IDs, including multiple variants. Do not deduplicate these rows. The older exploratory script used a different ampersand rule and could remove combining marks, so its normalized-name repetition/token counts are superseded by this report.

A concrete test-reference ambiguity: `S1-202327133` and `S1-628518958` are both `Lille Club SAS`, with addresses differing only in spacing/casing around `72-74 RUE Royale, Maison des associations, Lille, Hauts-de-France`. The conservative key collapses these differences. This does not prove the official identities are duplicates: test labels are unknown. Keep both reference IDs, preserve raw text, and record the ambiguity rather than merging them.

## 5. Train/test overlap

| Source | Shared IDs | Test rows with identical raw train payload | Test rows with equal normalized train payload |
| --- | --- | --- | --- |
| S1 | 0 | 0 | 0 |
| S2 | 0 | 0 | 1751 |
| S3 | 0 | 0 | 1356 |

Payload means name + address + country, excluding ID. Counts are test-record counts with at least one train counterpart, not join-pair counts. Some S2/S3 normalized payloads overlap while all IDs and raw payloads are disjoint. This can arise from cosmetic variants or ambiguous common names; it is not authorization to copy training labels onto test entities. No exact S1 payload overlap was found, but semantic/near-duplicate overlap has not been exhaustively ruled out.

## 6. Ground-truth integrity and cardinality

| Check | Measured value |
| --- | --- |
| rows | 2,206,821 |
| duplicate_s1_rows | 0 |
| missing_s1_rows | 0 |
| unknown_s1_rows | 0 |
| positive_links | 7,638,365 |
| duplicate_pairs | 0 |
| targets_with_multiple_s1_owners | 0 |
| wrong_target_prefix | 0 |

All positive-pair joins found their targets; country mismatches are zero. Source 1 truth coverage is exact. Target ownership uniqueness is a property of supplied labels, to be tested as a later postprocessing constraint.

| Country | S1 entities | Singletons | Singleton % |
| --- | --- | --- | --- |
| India | 883,188 | 49,351 | 5.59% |
| US | 1,323,633 | 73,896 | 5.58% |

The full match-count distribution is in [match_count_distribution.csv](match_count_distribution.csv). Keep singleton S1 rows even when expanding labels into positive pairs.

## 7. Full positive-pair analysis

| Country | Target source | True links | Equal name key | Equal address key | Either exact key | Missing target address |
| --- | --- | --- | --- | --- | --- | --- |
| India | S2 | 1,480,545 | 14.91% | 11.26% | 24.55% | 3.83% |
| US | S2 | 2,213,074 | 25.81% | 13.30% | 35.69% | 4.90% |
| India | S3 | 1,579,298 | 16.81% | 4.16% | 20.96% | 4.02% |
| US | S3 | 2,365,448 | 25.85% | 4.43% | 30.27% | 4.58% |

Address equality requires nonempty normalized address. The exact-key union is measured on true links only; its false-candidate volume and actual precision have not been measured. It is not a final blocking benchmark.

| Country | Target source | Both addresses have ASCII numeric tokens | No numeric token shared | Conflict fraction within numeric pairs |
| --- | --- | --- | --- | --- |
| India | S2 | 1,287,801 | 51,568 | 4.00% |
| US | S2 | 1,924,505 | 236,328 | 12.28% |
| India | S3 | 1,352,239 | 61,296 | 4.53% |
| US | S3 | 2,096,296 | 210,264 | 10.03% |

Numeric tokens here are simple `[0-9]+` substrings, not verified house or postal numbers. True matches can share none, so an absolute shared-number requirement would lose those links. Missing addresses are excluded from the numeric-pair denominator.

## 8. Exact-key oracle ceiling

| Country | Oracle macro F0.5 | All links retrieved, including singleton successes | Complete coverage among non-singletons |
| --- | --- | --- | --- |
| India | 0.439547 | 72,791 | 2.81% |
| US | 0.571623 | 143,047 | 5.53% |

Weighted across all training S1 entities, the oracle is **0.518766**. It selects every available true match and rejects every false candidate. Practical exact-key caps can only lower that ceiling. A union of fuzzy/rare-token/script-aware channels is the next retrieval experiment.

## 9. Sampled positive fuzzy similarity

Selection uses `hash(source1_entity_id,target_id) % 200 == 0` in pinned DuckDB 1.4.3. This is a deterministic approximately 0.5% pair sample, not a random split of S1 entities, and not a held-out validation set. Similarities use RapidFuzz `ratio` on the conservative keys with its 0-100 scale.

| Country | Target source | Sample pairs | Name ratio p10 / median / p90 | Name ratio below 50 |
| --- | --- | --- | --- | --- |
| India | S2 | 7,361 | 9.52 / 80.95 / 100.00 | 24.74% |
| US | S2 | 11,015 | 68.09 / 90.32 / 100.00 | 2.34% |
| India | S3 | 7,928 | 11.76 / 83.33 / 100.00 | 16.47% |
| US | S3 | 11,803 | 64.71 / 89.47 / 100.00 | 3.51% |

These are all positive pairs. Low similarities demonstrate why a single name threshold can miss true links, especially cross-script Indian records. They cannot establish classification accuracy or choose a safe threshold without hard-negative distributions.

## 10. Output verification and next steps

- All seven original-file SHA-256 values were rechecked and are unchanged.
- All six Parquet files match their database table row counts and aggregate row-content hashes.
- Python and SQL normalizers agree on 23,737 sampled records (both names and addresses).
- Focused regression tests cover Unicode marks, accent handling, number preservation, normalization parity/idempotence, strict TSV parsing and F0.5 edge cases.

Verification uses full row counts/fingerprints and a normalization sample; it is not a claim of independent manual inspection of 24 million records. Sources were never edited. Basic normalization was applied to all records, while richer cleaning, frozen splits, actual candidate generation, hard negatives and training remain separate work packages.

Proceed using the [two-person plan](../../docs/TEAM_PRETRAINING_PLAN.md). A owns tested multilingual/encoding/address views and storage; B owns frozen splits, metric, retrieval benchmarks and pair EDA. Do not begin model training until the stated handoff criteria are met.
