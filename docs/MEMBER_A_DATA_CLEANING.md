# Member A: data cleaning and record engineering

Your responsibility is to give the team reliable, reproducible representations of every business record. Work on all six source files. Member B consumes your versioned features to evaluate retrieval and later matching.

Read the [shared plan](TEAM_PRETRAINING_PLAN.md) and [measured findings](../reports/eda/EDA_FINDINGS.md) first. The workflow below separates the initial work already delivered from your remaining implementation tasks.

## What is ready now

- Full source-country quality report: `reports/eda/file_country_profile.csv`.
- Input checksums, collisions and cross-split checks: `reports/eda/full_audit.json`.
- Detailed script census and bounded text examples: `reports/eda/text_quality_details.json`.
- Basic normalizer: `scripts/normalization.py`.
- Raw fields plus `name_key`/`address_key` for every record: `data/interim/*_source*.parquet`.
- Reproducible import/audit script: `scripts/audit_dataset.py`.
- Regression tests: `tests/test_pretraining.py`.

The existing keys are conservative baseline comparison features. They do not resolve aliases, transliterations, address components or business identities.

## Your first session

1. Run the regression tests, inspect the input manifest and confirm your teammate has the same input hashes.
2. Read the quality report by country/source, including script census, format characters, control characters and placeholder-like names.
3. Inspect the bounded examples in `text_quality_details.json`. Some addresses contain encoding artifacts; some Indian-script names contain joiners; some names are the literal string `NA`.
4. Create a short `reports/eda/cleaning_decisions.md` log. For each proposed rule, write the observed problem, transformation, risk, example IDs and test needed.
5. Agree with B on normalization version, record schema and fixture IDs before expanding the feature set.

Runnable commands from the project root:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe scripts\audit_dataset.py --resume
.venv\Scripts\python.exe scripts\inspect_text_quality.py
```

The last two rerun the full audit/verification and are not needed after every tiny code edit. First run fixture tests; perform a full rebuild when the agreed normalization version changes. A changed version needs a new derived-data location, because audit resume rejects incompatible versions.

## A1. Data quality and ingestion

Maintain a seven-file allowlist and explicit schemas. Each source has `entity_id`, `business_name`, `business_address`, `country`; the label file has its two documented columns. Preserve ID strings exactly and keep text as strings, including literal `NA`.

Use tab-aware CSV parsing with proper quoting; do not split arbitrary text by commas or simply count physical lines as records. Validate UTF-8 strictly. Fail loudly on malformed input and record its location. The supplied files pass the current strict parser.

Record counts, hashes and schema in the output manifest. Check that no metadata file, output TSV or report is accidentally read as a dataset. Use the official data directory, not a recursive glob over the project.

**Deliverable:** a versioned input/quality manifest and a brief explanation of each anomaly. **Acceptance:** B can reproduce the counts and no IDs disappear between raw and derived files.

## A2. Correct multilingual normalization

The primary representation should retain Unicode letters, combining marks and numbers. Examples that must survive include Devanagari vowel signs, French accents and all house/unit numbers. Never transliterate the raw field in place.

Keep multiple views with explicit names:

| Proposed field | Transformation | Test |
|---|---|---|
| `name_key` | Current conservative NFC/lower/token-boundary key | SQL/Python parity and idempotence |
| `name_latin_accent_key` | Remove Latin accent marks only | `École` becomes `ecole`; `आदित्य` stays intact |
| `name_compatibility_key` | Optional NFKC view | Compare width variants and extra collisions |
| `name_transliterated` | Local script-aware transliteration | Actual labeled pairs from every observed script |
| `name_joiner_key` | Optional Indic joiner treatment | Compare with/without joiners without inserting accidental word breaks |

The current base key converts format characters into boundaries. That is an initial representation, not a final linguistic policy. ZWJ/ZWNJ treatment should be tested in a dedicated view because those characters can affect Indic shaping and token boundaries.

Use the measured script census. The dataset is not just English and Hindi: scope your tests to all scripts actually observed. Script detection is not language detection; Devanagari can represent several languages.

For apparent mojibake, add a flag and bounded repair experiment. Test local tools such as `ftfy` against fixtures; preserve the original string and record which repair fired. Do not apply a global Latin-1-to-UTF-8 round-trip to multilingual text. [ftfy documentation](https://ftfy.readthedocs.io/en/latest/)

**Deliverable:** implementation, transformation version, fixtures and before/after examples. **Acceptance:** no nonempty name collapses to empty without an explicit reviewed reason; no marks/numbers are lost from the primary view.

## A3. Business-name features

Implement contextual legal-form extraction rather than indiscriminate token deletion. Start from variants observed in the supplied development-training records and documentation. Keep `legal_form`, `name_core` and the full normalized name. Use token boundaries so a substring of a legitimate business word is not removed.

Explore domain-like names using local parsing only: split a name such as `maurewilliamscolombier.com` into a domain-label view. Do not open the domain. Compare concatenated name views as additional evidence; never assume a domain-looking string proves identity.

Keep order-preserving and order-insensitive token views. Preserve duplicate-token counts somewhere so token-set features do not hide all differences. Flag names with very few informative tokens for B's ambiguity analysis.

For literal `NA`, `unknown` or similar strings, preserve the original value and add `name_placeholder_like`. Do not mark every two-letter name as missing. B will determine whether strong address evidence can resolve these queries/candidates.

**Deliverable:** name-feature table and documented rules. **Acceptance:** B measures both improved true-link coverage and any increase in ambiguous candidates.

## A4. Address features

Extract numeric spans without guessing their meaning. Keep raw span, tokenized numbers and context. Examples `5 bis`, `5/105`, `5-105`, `J 105`, `0012`, and `12A` need separate fixtures.

Use contextual abbreviation views. `Rd` and `Road` can be useful variants; `St` can also mean Saint. Keep unexpanded text available. City/state/region candidates may be extracted from tokens or delimiters, but record confidence and allow multiple candidates when order is ambiguous.

Empty address means missing. Add a flag; never fill it using nearby rows, other entity IDs, labels or internet lookup. For parsed components, missing is distinct from agreement or disagreement.

Do not require shared numeric tokens, city text or a postal code as the sole retrieval route. Full labeled-pair evidence shows true links can disagree on numeric tokens. Pass features to B for graded scoring and complementary retrieval.

**Deliverable:** address-feature table, parsing confidence flags and an extraction-quality sample. **Acceptance:** all valid rows remain, and each proposed hard filter has measured positive-link losses.

## A5. Storage and reproducibility

Build versioned Parquet outputs, ideally partitioned by split/country/source for later experiments. Avoid excessive tiny partitions. Explicitly include the normalization version and input manifest hash in a sidecar manifest; do not depend on a notebook cell history.

Read and write bounded batches, select only needed columns, and use joins on compact IDs where possible. Begin with 50,000-100,000-record batches and adjust from measured memory. Do not treat a proposed batch size as a tested performance guarantee.

Never overwrite a validated feature version. A new rule produces a new version and new output directory. Verify row counts, ID coverage, raw-field preservation, data types and null semantics before handoff. Record runtime, peak memory and final disk size to inform the future SageMaker configuration.

**Deliverable:** clean record tables, manifest and command-line reproduction instructions. **Acceptance:** B can regenerate or read the features without importing A's interactive notebook state.

## What to remove or exclude

- Exclude `__MACOSX/`, `.DS_Store`, `._*`, environments and caches from dataset discovery and the submission archive.
- Normalize duplicate whitespace only in derived views.
- Exclude generic tokens from selected blocking indexes when necessary, but keep them in raw/full text.
- Do not delete repeated business names, duplicate-looking S2/S3 records, missing-address records, distractors, singletons, France records or long addresses.

Metadata files are already ignored in Git. Deleting them saves little space; the priority is preventing them from entering the pipeline. No destructive cleanup is required for this workflow.

## Handoff to Member B

Send the following together:

1. Feature schema and normalization version.
2. Source checksum manifest and row-count reconciliation.
3. Representative fixtures across all observed scripts and France.
4. Collision counts before/after each new view, especially distinct S1 IDs.
5. Missingness and parse-confidence definitions.
6. Read commands, memory notes and output paths.
7. Known failure modes and proposed ablation questions.

B returns candidate-recall changes, candidate-size changes and failure examples. Promote only rules supported by that evidence. Finish by reviewing B's split leakage checks and scorer before the team starts training.
