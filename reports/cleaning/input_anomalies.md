# Input anomalies: what they are, why they exist, what the pipeline does

Phase 1 deliverable ("a brief explanation of each anomaly"). Every number below is measured from the full data and can be reproduced from `manifests/input_manifest_v1.json`, `reports/cleaning/hygiene_change_counts.csv` and `reports/eda/full_audit.json`. Nothing here removes a row: no record is dropped, merged or altered in any input or derived raw field.

## Structural (parser level)

| # | Anomaly | Measured | Cause | Handling |
|---|---|---|---|---|
| 1 | **Values that start with a double quote** | train S1/S2/S3: 4 / 6 / 0 rows; **test S1/S2/S3: 134 / 349 / 330 rows** | The TSVs were written with standard CSV quoting: the value `"ehpad Club SAS` is stored as `"""ehpad Club SAS"` | Parse quote-aware (`quote='"'`, doubled quotes). A naive `split('\t')` corrupts exactly these rows. Python `csv`, DuckDB and the Parquet copy agree on every parsed value |
| 2 | Multi-line records | 0 (physical lines = rows + 1 in all seven files) | none | Recorded per file; the manifest fails if it ever changes |
| 3 | BOM, CRLF endings, tabs or newlines inside fields | 0 / 0 / 0 | none | Recorded per file; manifest fails on a BOM or mixed line endings |
| 4 | Non-dataset files next to the data | `.DS_Store` in `student_resource/dataset/`; `__MACOSX/` at the project root | Archive created on macOS | Explicit seven-file allowlist; metadata is listed as "never read"; an unlisted data-like file aborts the run |

## Text defects (kept in raw fields; flagged and repaired only in derived views)

| # | Anomaly | Measured (rows) | Cause | Handling |
|---|---|---|---|---|
| 5 | **Control characters** in name or address | train S1/S2/S3: 605 / 1,232 / 1,072; test: 529 / 1,365 / 1,180 | Upstream character-encoding damage (`Â\x80\x93`, `â\x80\x93`, U+001A). The damage is **shared** by a Source 1 record and its true S2/S3 match, so it does not break equality | `has_control` / `mojibake` flags; control characters become a boundary in `address_clean`. U+001A stands for a substituted dash *or apostrophe* (`Noor\x1aS Complex` = "Noor's Complex"), which is why a boundary (not deletion, not ftfy) is correct: it reproduces what the v1 key gives for a real apostrophe |
| 6 | **Zero-width non-joiner (U+200C)** inside Indic words | S2 / S3 train: 25,643 / 14,514; test: 31,104 / 17,468; none in S1 or in any address | Generated with the script's shaping character (Kannada, Telugu, Malayalam, e.g. the Telugu LLP `ఎల్‌ఎల్‌పీ`) | Deleted (not spaced) in `name_hyg`, so an Indic word stays one token. The v1 key splits such a word into several tokens. The raw string is unchanged |
| 7 | **Literal `NA`-style names** | 134 rows in total: train S2 6 + S3 18; test S2 49 + S3 61; S1: 0 | A name dropped upstream and replaced by a placeholder. **All 24 training cases are true links** (address nearly equal to their S1 record), so these are dropped names, not distractors | `name_placeholder_like` flag only; the string is kept and never converted to NULL. Retrieval must use the address for these rows |
| 8 | Repeated internal whitespace in names | S2 / S3 train: 554,392 / 575,616; test: 500,237 / 519,596; S1: 0 | A deleted token leaves a double space (`Bharat  Projects LLP`) | Collapsed in derived views; `name_multispace` flag kept |
| 9 | Missing addresses | S2 / S3 train: 168,967 (3.36%) / 175,916 (3.33%); test: 129,408 (2.65%) / 136,098 (2.68%); S1: 0 | Dropped upstream | `address_missing` flag; never filled from anything |
| 10 | Curly apostrophes, `N°` / `Nº` in France | addresses: test S1/S2/S3 2,091 / 51,728 / 52,216 rows changed by punctuation normalisation; no such characters in any name or in any train file | French addresses use `’` and `N°`/`Nº` | Normalised in `address_clean` (`’`→`'`, `N° 5`→`No 5`) |

## Semantic (data-level)

| # | Anomaly | Measured | Handling |
|---|---|---|---|
| 11 | **Repeated names** are not duplicates | Rows that repeat an already-seen name key (extra rows / rows): train S1 31.1%, S2 19.9%, S3 18.8% (EDA section 4) | Exact-name equality alone would create huge false blocks. Nothing is deduplicated |
| 12 | **Two French test reference records with the same normalised name+address** | `S1-202327133` and `S1-628518958` (both `Lille Club SAS`, `72-74 RUE Royale ...`) | Both IDs kept and recorded for the ambiguity register; never merged |
| 13 | Name-only keys become *less* selective after legal-form removal | Train S1 rows that sit in a shared-key group: v1 name key 35.8% (US) / 44.4% (India) vs `name_core` 47.7% / 53.6%; largest group 253 → 572 (US) | `name_core` is a gated matching view, never an identity key |
| 14 | Unlabeled France | 259,452 test S1 records, no France labels anywhere | Rules are country-independent or country-scoped with a generic fallback; no French score is claimed |
| 15 | No compatibility-normalisation effect | `name_compat_key` (NFKC) differs from the v1 key in **0** rows of all six files | The view is emitted for completeness but has no measured value; Phase 8 may drop it |

## What was verified, independently

- Row counts, per-country counts, blank addresses and SHA-256 agree across the Python strict parser, DuckDB's parse of the raw TSV, the Parquet copies and `reports/eda/full_audit.json`.
- Flag counts (control, format, repeated whitespace, missing address, placeholder) equal the audit's separate SQL counts for every file and country.
- `text_hygiene.lmn_key` reproduces the DuckDB-computed v1 keys on all 24,229,173 rows (0 differences).
