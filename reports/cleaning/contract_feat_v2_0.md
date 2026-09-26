# Contract between Member A and Member B for `feat_v2_0`

Status: **proposed by A on 25 September 2026; Member B has not yet confirmed.** Items B must answer are marked **[B]**. Nothing below has been agreed verbally or in writing by B; do not treat it as signed off until B replies.

## 1. What is fixed now (verified, not a proposal)

| Item | Value | How to verify |
|---|---|---|
| Raw inputs | Seven files under `student_resource/dataset/`; SHA-256 list in `reports/cleaning/baseline_hashes.txt` | `python scripts/check_baseline.py` prints `OK` for all seven and exits 0; B compares the text file with their own hashes |
| Input manifest | `manifests/input_manifest_v1.json`, SHA-256 in `manifests/input_manifest_v1.sha256` | `python scripts/build_manifest.py --check` rebuilds and requires a byte-identical file |
| Row counts | 24,229,173 source rows; 2,206,821 label rows; 7,638,365 positive links | Python strict parse, DuckDB raw parse, Parquet copy and the audit agree (manifest `reconciliation`) |
| Parsing rule | Quote-aware TSV (`quote='"'`, doubled quotes); values that start with `"` exist (134 / 349 / 330 rows in test S1 / S2 / S3) | A naive `split('\t')` corrupts them; use the manifest's parser settings |
| Frozen v1 rule | `scripts/normalization.py` (`nfc_lower_lmn_v1`); columns `name_key`, `address_key` in `data/interim/*.parquet` | Never edited. `text_hygiene.lmn_key` reproduces it exactly on all 24.2M rows (Phase 2 scan) |
| Environment | `requirements-features.txt` (pyarrow 25.0.1, anyascii 0.3.3, psutil 7.2.2, ftfy 6.3.1 added; licenses checked) | `uv pip install --python .venv\Scripts\python.exe -r requirements-features.txt` |

Guard for every later stage: `cleaning.manifest.assert_inputs_match_manifest(root, 'manifests/input_manifest_v1.json')` fails if any input file changed.

## 2. Versions, paths and naming (proposed)

- `FEATURE_VERSION = feat_v2_0`, `HYGIENE_VERSION = hyg_v2_0` (`src/cleaning/__init__.py`).
- Output location of the full feature table (**built and verified**, see 3c): `data/features/feat_v2_0/split=<train|test>/source=<1|2|3>/country=<label>/part-*.parquet` plus `_manifest.json` and `_run.json`. A validated version directory is never overwritten; a rule change creates `feat_v2_1`.
- Join key: `entity_id` (exact string). `id_num` (integer suffix) is a compact join key. **Neither may be a model feature.**
- Downstream artifacts record two hashes: the input manifest SHA-256 and the feature-manifest SHA-256.
- The repository is not under git; source revisions are recorded as a SHA-256 over the feature-defining files of `src/cleaning/` (code and lexicons; the verification-only modules are excluded so that checking a table never invalidates it). Whether to `git init` is left to the user (decision D2 below).

## 3. What A hands over after Phase 2 (implemented and verified)

Function: `cleaning.text_hygiene.hygiene_record(name, address)` returns these columns. Strings are never `None`; an empty view is `''`.

| Column | Meaning |
|---|---|
| `name_hyg` | v1-style key after safe repairs: control/mojibake separators, ZWNJ/ZWJ deleted, curly quotes/dashes/`N°`, dotted **lexicon** acronyms joined (`L.L.C.`->`llc`) |
| `name_latin_accent_key` | Accent fold on Latin bases only, plus ligatures (`œ æ ß ø ł đ`); nothing else changed |
| `name_joiner_key` | Only ZWNJ/ZWJ deleted (isolates that one rule for ablation) |
| `name_compat_key` | NFKC view (evaluate, do not assume it helps) |
| `name_apos_join_key` | Like `name_hyg` but apostrophes deleted instead of split (decision D5: both views exist; B chooses by measured collisions) |
| `name_repairs`, `address_repairs` | Comma list, pipeline order, of the repairs that changed the string: `nfc, controls, joiners, punct, dotted, ws` |
| `name_has_control`, `name_has_format`, `name_mojibake`, `name_multispace` | Booleans on the raw name (same for `address_*`) |
| `address_clean` | Case- and punctuation-preserving text: commas, digits, marks and zero padding kept; mojibake/control separators removed; `’`->`'`; `N°`/`Nº` before a digit -> `No ` |
| `address_missing` | Address is empty after stripping. Never filled from anything |

Flag definitions: `has_control` = any Cc character; `has_format` = any Cf character; `mojibake` = any U+0080-U+009F or U+001A; `multispace` = two or more ASCII whitespace characters in a row.

Fixtures for these views: `tests/fixtures/hygiene_fixtures_v2.jsonl` (33 cases; raw strings copied verbatim from the data by entity ID, expectations written by hand). Every case that names an entity ID can be looked up by B.

### 3b. Added by Phases 3 and 4 (implemented and verified; `cleaning.names.build_name_features(raw, country)`)

| Column | Meaning |
|---|---|
| `legal_form`, `legal_form_pos` | Canonical codes ordered by rank, `+`-joined (`PVT+LTD` for Private Limited, Pvt. Ltd., and the native-script forms alike); position `suffix` / `prefix` / `middle` / `bracket` / `mixed` / `none`. Lexicons are **country-scoped**: `private` is legal in India only, `sci` in France only; an unknown country gets the generic tier plus the script-specific native tier |
| `name_core` | Tokens without legal forms, injected leading words (`The`, `Dr`, `Mr`, `Sri`, `Shri`, `Smt`, raw `M/s`), the connector `and`, and a domain's `www`/`com`. Never empty for a non-empty name (`name_core_fallback` marks names made only of legal words). **A matching view, not an identity key**: it raises the share of S1 names that share a key (US 35.8% -> 47.7%) |
| `name_core_fold`, `name_core_set`, `name_core_compact` | Accent/ligature-folded, sorted-unique and space-free variants of the core (order-, accent- and spacing-insensitive) |
| `name_core_trim` | **Experimental.** Core without trailing filler words (`Center`, `Services`, `Summit` ...) fitted from unlabeled S1-vs-S2/S3 lift; +0.5 to +2.0 points, more collisions |
| `name_leading_removed`, `name_bracket_text`, `name_token_counts`, `name_ntokens`, `name_ncore`, `name_ninformative` | What was removed, bracket contents, duplicate-token counts, token counts, and the number of core tokens outside the per-country generic list |
| `name_is_domain_like`, `name_domain_label` | Local parse of `x.com` names (only `.com` occurs). Nothing is ever fetched |
| `name_placeholder_like` | `NA`-style names. **All 24 such training targets are true links**; retrieval must use the address for them |
| `name_noise_prefix` | Decorative prefix (`**`, `>>`, `..`, `--`, `#`, `@`) |
| `name_alias_marker`, `name_alias_left`, `name_alias_right` | `d/b/a`, `a/k/a`, `f/k/a`, `t/a`, `trading as`. Only Source 3 carries them (0.7-1.0% of S3 names); the part after the marker is what the reference usually contains (+2.9 / +3.5 points on S3) |
| `name_scripts` | Bitmask over Latin, the nine Indic scripts, Other. **Verified cell by cell against the EDA script census.** Script is not language |
| `name_translit` | ASCII rendering (`anyascii`; accents and ligatures fold too). Auxiliary view; the raw name is never transliterated in place |
| `name_skeleton` | Coarse phonetic skeleton of the transliterated core, iterated to a fixed point, applied identically to Latin and native names. **Use as graded similarity, not as an equality key**: an exact skeleton hit shares its key with a median of 60 S1 names and only 9.9% of hits are unique |

Measured evidence for B (all provisional, 5% pair samples; re-run on B's dev fold once it exists):

- India cross-script true pairs (27,230): v1-key similarity median 10 -> skeleton 92.3, with 93.6% of pairs >= 80. Legal-form codes agree with the Latin reference on **100.0%**.
- Retrieval among 479,954 unique S1 India names (`reports/cleaning/neural_bakeoff.md`, GPU): graded skeleton similarity recall@10/@100 = 82.8% / 95.9%; LaBSE 78.8% / 89.7%; the union of both top-10 lists **93.6%**. LaBSE (Apache-2.0, 471M parameters) is therefore a useful *complementary* channel for R7; multilingual-e5-small is not. Tamil is the weakest script for both.

### 3c. Added by Phases 5 and 6 (implemented and verified; `cleaning.addresses.build_address_features(raw, country)` and the table itself)

**Address columns.** Lists are never NULL (`[]` = nothing found), strings are never NULL, a missing address is the flag `address_missing`. Everything is derived from the raw address; nothing is ever filled from other rows, IDs or labels.

| Column | Meaning |
|---|---|
| `address_segments` | Comma segments after canonicalisation, original order. A state segment is replaced by its canonical name (`NY`, `New York`, `MH`, `महाराष्ट्र` -> `new york`, `maharashtra`); junk segments (`null`, `n/a`, India `DIVREPORTINGCIRCLE`) and injected components (A-11, A-12) are removed; the number label `no` is dropped before a number (also across a comma); leading zeros are stripped; US/France abbreviations are expanded per the country tier |
| `address_canon`, `address_tokset`, `address_segset`, `address_nsegments` | Segments joined by spaces; sorted unique tokens; sorted unique segments joined by `\|`; segment count. Use the set views for order-insensitive comparison (S3 shuffles components); the ordered view is kept |
| `address_numbers_raw`, `address_numbers_canon`, `address_number_ctx` | Parallel lists: each number span as written (`5-105`, `J 105`, `12A`, `5 bis`, `3-277/1`), its canonical form (zeros stripped per component, `J 105` -> `j105`), and the 1-2 preceding tokens as context (`h no`, `po box`, `hn`). **No meaning is assigned** (house, unit and postal numbers are not distinguished). Spans are taken from the cleaned text, so an injected number (`PO BOX 2989`, `HN 711`) is still listed, with its context. Measured: true pairs share no numeric span in 10.7-13.8% of pairs with numbers on both sides, so never a hard filter |
| `address_postal_candidates` | Runs of exactly 5 or 6 digits. Candidates only, never called ZIP/PIN |
| `address_state_canon`, `address_state_conf` | Canonical state/region and how it was found: `exact` (English name), `alias` (code or alias), `mapped_native` (native-script form, India), `mapped_department` (France, département -> region), `conflict` (two different states, canon empty), `none`. **Not a veto**: on India true pairs 98.6% agree and all 1.3% disagreements are S1 `Telangana` vs S2/S3 `Andhra Pradesh`; a US city named like a state (`Wyoming, Illinois`) gives `conflict` |
| `address_city_candidates` | Up to 3 segments without digits/street words, nearest to the state segment first (else last segments first). A hint, not a parse |
| `address_scripts` | Script bitmask of the raw address (same bits as `name_scripts`) |
| `address_null_tokens`, `address_had_leading_zero`, `address_extras` | Number of junk segments dropped; whether a zero-led digit run existed; the removed injected components, ` \| `-separated (US: `cdp`, `pmb n`, `po box n`; India: `hn n`, `b3`, `<x> region`) |
| `address_parse_conf` | `missing` (no address), `high` (state found by name/code/alias/native/département **and** at least one number span), `medium` (one of the two), `low` (neither). A descriptor for B, not a filter |

Fixtures: `tests/fixtures/address_fixtures_v2.jsonl` (90 cases; addresses copied verbatim from the data by entity ID, expectations written by hand, 14 real true pairs).

**Physical table (Phase 6).**

- Path: `data/features/feat_v2_0/split=<train|test>/source=<1|2|3>/country=<label>/part-<input table>-<first row group>.parquet` (country values are URL-quoted in the path). 15 partitions (France exists only in `split=test`), 251 files, ZSTD, 24,229,173 rows, 69 columns, one row per entity. `split`, `source` and `country` are also stored inside the files, so the table can be read with or without `hive_partitioning`.
- Read it with `duckdb.read_parquet('data/features/feat_v2_0/**/*.parquet', hive_partitioning=true)` (see the README). Column order and types are fixed by an explicit Arrow schema (`cleaning.record.SCHEMA`; no type inference); nothing is nullable.
- Identity and raw fields (`entity_id`, `id_num`, `source`, `split`, `country`, `business_name`, `business_address`, `name_key`, `address_key`) are copied unchanged and verified against the input manifest (content hash sum equals the manifest for all six tables). **`entity_id`, `id_num`, `source` and `split` are join keys, never features.**
- `_manifest.json` (deterministic: versions, input-manifest and source-tree SHA-256, lexicon hashes, schema, every file with rows and bytes) and `_run.json` (wall time, memory, library versions, command). A finished version is never overwritten.
- Build: `python scripts/build_features.py` (6 workers); verify: `python scripts/verify_features.py --version feat_v2_0` (files, coverage, NULLs, 74 independent SQL invariants, reproduction of the earlier full scans, Python recomputation, determinism). Results: `reports/cleaning/feature_verification_feat_v2_0.json`.

## 4. Requests to B **[B]**

1. **Freeze `fold_manifest.parquet` before A fits any label-derived mapping** (native-script state names, transliteration choice, generic-token lists derived with labels). Until then A uses only unlabeled statistics and manual lexicons.
2. Confirm that A's fixture IDs (listed in `reports/eda/cleaning_decisions.md` and the fixtures file) are acceptable as the shared regression set, and add B's own.
3. Confirm that neither member feeds `entity_id`, `id_num`, `source`, `split` or `country` to a learned model as raw features (country as a blocking key is B's call).
4. Confirm the view naming above, especially that `name_hyg` (not `name_key`) is the recommended base for new retrieval channels, while `name_key`/`address_key` stay available unchanged.
5. Say which of the `name_*_key` views B wants first for benchmarking. All are in the built table (`data/features/feat_v2_0`, section 3c) and available for any single row via `hygiene_record`.

## 5. Decisions

| # | Decision | Status |
|---|---|---|
| D1 | Add `pyarrow`, `anyascii`, `psutil`, `ftfy` via `requirements-features.txt` | **Done** (installed, versions pinned) |
| D2 | `git init` so source revisions can be logged | **Not done**: creates a `.git` directory and is the user's call. A source-tree hash is used meanwhile |
| D3 | v2 fields computed in Python, DuckDB for verification and ablation | Followed |
| D4 | B freezes the fold before label-derived mappings | **Open** [B] |
| D5 | Apostrophe/elision policy | Both views emitted for names (`name_hyg` splits, `name_apos_join_key` joins); addresses use the splitting form only (`d'angesr` -> `d angesr`); final choice in Phase 8 |
| D6 | Who reviews `generic_tokens_<country>.tsv` | Open; A curates, B challenges with hard-negative evidence |
| D7 | Rule changes after the first full build | Four address rules were added after reviewing the built table (A-11..A-14 in the decisions log) and the table was **rebuilt and re-verified as the same version `feat_v2_0`** because no consumer had read the first build. From now on any rule change creates `feat_v2_1` |
| D8 | Trailing `city`/`county`/`township` view for US addresses (+1.2 to +1.8 pp measured) | Open [B]: proposed as an extra column in `feat_v2_1`, not a change of `address_canon` |
