# Amazon ML Challenge 2026: two-person cleaning and EDA plan

Prepared: 25 September 2026. Scope: data preparation, EDA, validation design, candidate-generation experiments, and the handoff to future model training.

## 1. What you should do together

Assign **Member A to data engineering and normalization** and **Member B to label analysis, validation, and candidate retrieval**. Both people work with all three sources and all countries. Splitting by country or giving each person half the rows would create incompatible cleaning rules and leave shared identity relationships unresolved.

The objective before training is a reproducible dataset with preserved source records, measured noise, a frozen validation split, and a candidate generator whose missed matches and computational costs are known. A dataset that merely looks tidy is insufficient: changes must preserve the evidence needed to identify businesses.

Personal runbooks:

- [Member A: cleaning and data engineering](MEMBER_A_DATA_CLEANING.md)
- [Member B: EDA, validation and candidates](MEMBER_B_EDA_VALIDATION.md)
- [Measured audit findings](../reports/eda/EDA_FINDINGS.md)
- [Full audit JSON](../reports/eda/full_audit.json)

The new audit finds that exact normalized name-or-address equality retrieves only 28.80% of labeled links. It also identifies nine Indian scripts, control/format-character issues, literal `NA` names, and one normalized collision between two French test S1 records. These observations drive the division of work below; the cleaning stage cannot safely reduce this to English lowercase strings or drop duplicate-looking rows.

## 2. Current work versus remaining work

This repository includes a reproducible full-data audit and a first conservative cleaning representation. The JSON field `complete: true` indicates a finished audit. The first-stage output preserves all original source fields and adds `name_key` and `address_key`; it does not claim that typo resolution, transliteration, or business identity resolution is complete.

| Work item | Status / scope |
|---|---|
| Read challenge rules, schema, validator and supplied documentation | Reviewed |
| Full source-file profiling and ground-truth checks | Executed by `scripts/audit_dataset.py`; results in audit report |
| Basic Unicode-safe comparison keys | Implemented, tested, applied to every source record |
| Raw-preserving Parquet copies | Produced by full audit under `data/interim/` |
| Positive-pair exact-equality analysis | Full training-label analysis |
| Positive-pair fuzzy similarity exploration | Deterministic approximately 0.5% pair sample; explicitly not a full fuzzy comparison |
| Split construction and split-leakage gates | Specified below; not yet executed |
| Transliteration, legal-form and contextual address views | Experiments assigned to A; not yet applied |
| Candidate generation and hard-negative profiling | Assigned to B; not yet executed |
| Training-ready pair features | Assigned after candidate selection |
| Training / validation model score | Not performed; no model score is claimed |

An exact-key **oracle ceiling** in the audit is a diagnostic: it assumes perfect classification of all true matches retrieved by that rule. It is neither achieved classifier performance nor a leaderboard result.

## 3. What the source files represent

Source 1 is the reference. Each Source 1 entity needs zero, one or several matches in Source 2 and Source 3. Different S2/S3 record IDs must be retained even when their text is identical.

| File | Records | US | India | France |
|---|---:|---:|---:|---:|
| train_source1.tsv | 2,206,821 | 1,323,633 | 883,188 | 0 |
| train_source2.tsv | 5,034,616 | 3,016,817 | 2,017,799 | 0 |
| train_source3.tsv | 5,285,603 | 3,170,056 | 2,115,547 | 0 |
| test_source1.tsv | 1,732,544 | 663,106 | 809,986 | 259,452 |
| test_source2.tsv | 4,887,273 | 1,871,330 | 2,312,565 | 703,378 |
| test_source3.tsv | 5,082,316 | 1,945,701 | 2,405,000 | 731,615 |

There are 24,229,173 source records and 2,206,821 ground-truth rows. The seven TSV files total 2,520,573,701 bytes. In memory, decoded strings, hash tables, joins and candidate pairs can occupy much more than their file sizes.

The training labels contain 7,638,365 links, including 3,693,619 to S2 and 3,944,746 to S3. There are 123,247 singleton S1 entities (5.5848%). Maximum observed match count is 11; do not enforce 11 as a test-time cap because it is only a training observation.

France is absent from training labels and contributes 259,452 test queries. India is also a larger share of test than training. Treat the country field as open-ended and report metrics separately by country and source.

## 4. Ownership and boundaries

| Package | Accountable owner | Reviewer | Deliverable |
|---|---|---|---|
| A1: input inventory, checksums, strict ingestion | A | B | input manifest and row reconciliation |
| A2: field quality, scripts and missingness | A | B | field-level EDA and quality flags |
| A3: Unicode, names and address normalization | A | B | versioned normalization functions and fixtures |
| A4: Parquet layout and reusable record features | A | B | clean record tables and schema contract |
| B1: labels, singleton/cardinality and ambiguous records | B | A | label-integrity report and ambiguity register |
| B2: split design and official metric | B | A | split manifest, scorer and leakage tests |
| B3: candidate rules, retrieval and size control | B | A | candidate tables and measured recall/cost |
| B4: pair EDA, hard negatives and training handoff | B | A | pair-feature specification and error taxonomy |
| Joint: choose cleaning/rules using evidence | Both | Both | signed-off normalization/retrieval versions |

A owns changes to normalization. B owns the validation split and candidate schema. The other member can propose changes, but both approve changes that invalidate existing caches or benchmark results. Neither should silently edit the other's generated files.

## 5. Shared technical contract

### Existing files created for this phase

```text
docs/
  TEAM_PRETRAINING_PLAN.md
  MEMBER_A_DATA_CLEANING.md
  MEMBER_B_EDA_VALIDATION.md
scripts/
  audit_dataset.py
  inspect_text_quality.py
  write_eda_findings.py
  normalization.py
tests/
  test_pretraining.py
requirements-eda.txt
reports/eda/
  full_audit.json
  text_quality_details.json
  verification.json
  EDA_FINDINGS.md
  file_country_profile.csv
  positive_pair_profile.csv
  match_count_distribution.csv
  positive_pair_sample_s2.csv
  positive_pair_sample_s3.csv
data/interim/
  audit.duckdb
  train_source1.parquet ... test_source3.parquet
```

`data/interim/` is derived data, and `.venv/` is the isolated Python environment. The source TSVs stay in `student_resource/dataset/`. Never use a broad recursive `*.tsv` load over the workspace: it may load Apple metadata, reports, samples, or output files as input.

### Current record schema

| Column | Type | Purpose |
|---|---|---|
| entity_id | string | Exact original ID, never a model feature |
| business_name | string | Original parsed name, retained |
| business_address | string | Original parsed address; empty remains empty |
| country | string | Original label, open vocabulary |
| name_key | string | NFC + lowercasing + Unicode letter/mark/number tokens |
| address_key | string | Same conservative normalization for address |

The source and split are encoded in the file name for this initial copy. In the next feature version, include explicit `source`, `dataset_split`, `normalization_version`, and a stable row locator. Entity IDs may be mapped to integer surrogate keys internally to reduce memory, but the exact string IDs must be reconstructible and never fed to a learned model.

### Planned richer record schema

Add fields only after their tests and ablations exist: `name_latin_accent_key`, `name_transliterated`, `name_core`, `legal_form`, `address_tokens`, `number_tokens`, `postal_candidates`, `name_script_flags`, `address_script_flags`, `address_missing`, and per-feature validity/confidence flags.

Do not call a six-digit number a confirmed Indian PIN or a five-digit number a confirmed French/US postal code based on length alone. House/unit numbers can have the same pattern. Store it as a candidate with context.

### Planned candidate/pair schema

| Field | Meaning |
|---|---|
| source1_entity_id, candidate_entity_id | Unique pair key |
| country, candidate_source | Query country and S2/S3 |
| retrieval_methods | All rules that retrieved this pair |
| name_retrieval_score, address_retrieval_score | Separate score channels |
| name_rank, address_rank | Rank within each retrieval method |
| fold | Frozen split assignment |
| normalization_version, candidate_version | Cache and result provenance |

Store one candidate pair per row in Parquet during development. Produce the comma-separated list format only at the final export stage. Do not store millions of text pairs in pandas object columns if a join on IDs is sufficient.

## 6. Reproducible local commands

Run from `C:\SideQuest\ML Challenge`. The current environment is already provisioned with Python 3.12 and the two pinned EDA dependencies.

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe scripts\audit_dataset.py --resume
.venv\Scripts\python.exe scripts\inspect_text_quality.py
.venv\Scripts\python.exe scripts\write_eda_findings.py
```

For a teammate's fresh clone with Python 3.12 available:

```powershell
uv venv .venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -r requirements-eda.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe scripts\audit_dataset.py
.venv\Scripts\python.exe scripts\inspect_text_quality.py
.venv\Scripts\python.exe scripts\write_eda_findings.py
```

The first run imports every input, profiles each source/country, exports Parquet, checks overlap and ground truth, and computes positive-pair diagnostics. `--resume` reuses imported source tables only when the recorded input checksum and normalization version match. Run one audit process at a time. Do not concurrently write the DuckDB database from two programs.

The audit currently uses a 2 GB DuckDB memory limit and two threads. That limit is not a guarantee about total Python/process RAM. The machine has approximately 16 GB RAM; keep other memory-heavy work modest. Use Parquet reads with selected columns and SQL aggregation, and inspect only bounded samples in a notebook. DuckDB documents larger-than-memory execution and limitations of blocking operations; choose batch sizes from measured peak memory. [DuckDB workload guidance](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads)

The parser sets tab delimiter and string types, keeps empty fields as empty strings, and uses strict error handling. Silent row skipping is unacceptable. Literal `NA`/`NULL` text should not become missing just because a parser guesses so. [DuckDB CSV options](https://duckdb.org/docs/current/data/csv/overview)

## 7. Member A's cleaning method

### A1. Protect and reconcile inputs

1. Use the seven-file allowlist; record SHA-256, byte size, column names and row counts.
2. Confirm strict UTF-8 parsing and unique IDs inside each source. Check train/test ID overlap independently.
3. Preserve every original field, including punctuation, accents, casing, and empty strings.
4. Compare row counts before and after each transformation. Any unexplained row loss fails the stage.
5. Quarantine a malformed row with its file, location and reason if encountered; do not silently remove it. A malformed test S1 row still needs to be resolved because every test query needs output.

### A2. Unicode and whitespace

The initial `nfc_lower_lmn_v1` representation performs NFC normalization, lowercasing, replacement of non-letter/mark/number runs by one space, and edge whitespace trimming. Unicode categories `L`, `M`, and `N` are retained. The inclusion of `M` is critical for Devanagari vowel signs and other combining marks.

Avoid `re.sub(r'[^\w]+', ' ', text)` as a general multilingual cleaner: Python's word-character class does not retain every combining mark. Also avoid deleting every non-ASCII character or globally stripping every diacritic. The old exploratory `tmp/profile_dataset.py` used the unsafe word-character approach, so its normalized token/collision counts should not be used as canonical measurements. Use the new report instead.

NFKC may be useful as an additional comparison view for width/compatibility variants, but evaluate its collisions before promoting it. NFC preserves canonical equivalence with fewer compatibility changes. Unicode defines the normalization forms and distinguishes canonical from compatibility equivalence. [Unicode UAX #15](https://www.unicode.org/reports/tr15/)

The full script census includes Devanagari, Bengali, Gujarati, Gurmukhi, Odia, Tamil, Telugu, Kannada and Malayalam. Build fixtures across all nine. Some records contain U+200C ZERO WIDTH NON-JOINER; the current basic key replaces it with a boundary, so test a separate joiner-aware view before adopting that behavior as final. Some addresses contain mojibake/control characters: keep the raw text, add a flag, and test a bounded local repair view. A tool such as ftfy offers heuristic Unicode repair, but it does not remove the need to validate edits on these records. [ftfy documentation](https://ftfy.readthedocs.io/en/latest/)

### A3. Names: several views, each with a purpose

| View | Intended benefit | Guardrail |
|---|---|---|
| raw | Human review and original evidence | Never overwrite |
| conservative key | Case/punctuation/spacing robustness | Preserve letters, numbers and marks |
| Latin accent-folded key | École/Ecole style variants | Strip marks only for Latin bases |
| transliterated view | Latin/Devanagari retrieval | Auxiliary only; measure collisions and actual labeled recall |
| legal-form/core view | Pvt/Ltd/Inc variants | Extract suffix separately; do not remove generic words everywhere |
| token-sorted view | Word-order variation | Keep unsorted view and token multiplicity too |
| domain-like name view | Company name versus company.com | Local text parsing only, no website requests |

The existing `latin_accent_key` helper is tested but has not been applied to all rows. Transliteration still needs a chosen local library, license review and labeled-pair benchmark. No internet translation or business lookup is part of this workflow.

Mappings such as `pvt`/`private` or `ltd`/`limited` should be versioned and boundary-aware. `&` becomes a token boundary in the current base key; English `and` and French `et` expansions belong in separate language-aware experiments. Do not blindly replace every `st` by `street`: it can mean Saint. Avoid stemming, general stopword removal and global spell correction on business identities.

### A4. Addresses: preserve detail and represent uncertainty

Keep the original address and conservative key. Add separate representations for token order, numeric tokens and contextual abbreviations. Preserve `5`, `5 bis`, `5 ter`, `5/105`, `5-105`, `0012`, units and letter-number combinations. The base token view splits punctuation, so retain the raw structured number span too; `5-105` must not become identical to `5105`.

Do not invent missing addresses, forward-fill from neighboring rows, or copy an S1 address into its labeled S2/S3 record. Labels are for evaluation/training, not for modifying inference inputs. A missing address receives an indicator; its comparison score is undefined or explicitly missing, never evidence of a perfect match with another missing address.

Different numeric tokens are useful conflict evidence, but not a universal veto. The observed true pair `J 105` versus `J 5-105` is one reason to evaluate this on labels first.

Postal extraction, cities and states should be tentative without a verified parser. Use supplied text and training-derived mappings; government registries, geocoding and external address enrichment are prohibited by the challenge.

### A5. Acceptance for cleaning v2

- Same exact IDs and row counts as v1, with no label columns mixed into input features.
- Devanagari, accents and address-number regression fixtures pass.
- Normalization is deterministic and idempotent.
- Raw fields can be compared back to the parsed inputs.
- Nonempty-to-empty transformations are measured and reviewed.
- New normalized collisions are measured, especially among different S1 IDs.
- Cleaning ablations report both recovered true links and added candidate ambiguity.
- A version bump invalidates the affected candidate/feature caches.

## 8. Member B's EDA, splits and candidate method

### B1. Labels and ambiguity

Expand the comma-separated ground truth into one positive pair per row, while retaining the original S1 table so singleton queries are not lost. Assert one ground-truth row per S1, valid S2/S3 targets, no duplicate pairs and no unexpected target reuse.

The observed labels assign every positive S2/S3 ID to exactly one S1 and preserve country. A one-owner rule is therefore a useful hypothesis for later postprocessing, but it is not a separately stated submission-format requirement. Benchmark its effect before enforcing it. Country equality is a strong observed blocking rule, not proof that mislabeled countries could never occur in an unseen set.

Inspect identical or near-identical S1 name/address combinations that correspond to different IDs. If two reference records have indistinguishable supplied features, no text cleaner can create evidence that is absent. Record such cases, group them for a stricter validation stress test, and do not 'fix' them by merging reference IDs or altering labels.

The current exact tuple is unique in training Source 1, but two French test records (`S1-202327133` and `S1-628518958`, both Lille Club SAS) share it after spacing/case normalization. Preserve both IDs and record the ambiguity. An exact-payload grouping split therefore adds no grouping changes to this particular training version; a near-duplicate stress split requires a separately tested similarity rule.

### B2. Freeze splits before further label-guided changes

Use S1 identity groups, with all of their positive S2/S3 records kept in the same fold. Suggested initial split is 80% development training, 10% validation for decisions, and 10% locked local holdout; these percentages are a team choice, not a challenge requirement.

Stratify at S1 level by country and match-count bucket `0,1,2,3-4,5+`. Audit balance for S2/S3 presence, script and missing-address slices. Save exact assignments and a stable seed; never split expanded pair rows randomly.

For a stricter split, group S1 IDs that share the same conservative `(country,name_key,address_key)` before assignment. For broader alias/chain groupings, inspect group-size distributions first: a ubiquitous business name can otherwise create enormous components. Run the ordinary entity split and the stricter ambiguity split as separately named protocols.

Negative records also require a policy. For an isolated benchmark, assign each labeled target to its owner's fold; assign unmatched S2/S3 records deterministically to a fold. Build each fold's retrieval index from that fold's target records, so the same record cannot become a training negative and a validation positive. A reduced corpus changes retrieval difficulty, so also measure sampled held-out queries against the full training target corpus as a separately named full-corpus retrieval stress test. Do not mix those results.

After the split is frozen, learn alias dictionaries, token frequencies, IDF weights, thresholds and feature selections from the development-training fold only. Read validation/test records to transform and index the records being retrieved, but do not learn supervised mappings from their labels. Any corpus-fitted unsupervised retrieval statistics must be documented and reproduced consistently across folds and final inference. Frozen training-fitted vocabulary/weights are the conservative default. Scikit-learn documents why fitted preprocessing must respect data splits. [Data leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html)

The full-label descriptive audit already performed is exploratory evidence; it cannot also be called an untouched holdout experiment. Freeze the split now, stop iterative inspection of locked-holdout errors, and document that earlier aggregate exposure.

### B3. Implement the actual metric

For each S1, let `TP`, `FP`, and `FN` be set intersection/difference counts. Compute:

```text
F0.5_i = 1.25 * TP / (1.25 * TP + FP + 0.25 * FN)
```

Special case: empty truth and empty prediction scores 1; empty truth and nonempty prediction scores 0. Average over every S1 in the evaluation fold, including queries with no candidate or no prediction. Do not average only nonempty predictions and do not substitute pairwise micro-F1.

In this count form, one FP contributes four times the denominator penalty of one FN. Threshold 0.5 is not intrinsically optimal. The `entity_f05` helper has tests covering the official example and singleton cases, but a full dataset scorer remains a B deliverable.

### B4. Candidate generation: implement separate retrieval passes

The test comparison universe is 17,272,751,604,416 pairs. Even same-country all-pairs comparisons total 6,724,569,566,212. Similarity functions must operate after retrieval reduces that universe.

Build candidate sets from a union of independent rules:

| Pass | Rule | Why needed |
|---|---|---|
| R1 | Country + exact conservative name | Cheap, useful for address-missing records |
| R2 | Country + nonempty exact conservative address | Finds aliases where business names differ |
| R3 | Country + rare name token combinations | Tolerates suffixes and word-order changes |
| R4 | Country + rare address token / contextual number combinations | Handles name corruption |
| R5 | Character n-gram name retrieval | Typos and abbreviations |
| R6 | Character n-gram address retrieval | Partial/noisy addresses |
| R7 | Transliteration/Latin-accent auxiliary retrieval | Different scripts and French accents |
| R8 | Fallback for weak/no-candidate queries | Stops strict early rules from becoming permanent misses |

Implement R1 and R2 as separate equality joins, then concatenate and deduplicate pairs. Avoid one huge SQL join with `name_equal OR address_equal` or a fuzzy function over the country cross-product. Splink's documentation explains the performance benefit of equality joins and separate blocking passes. [Blocking performance](https://moj-analytical-services.github.io/splink/topic_guides/blocking/performance.html)

Exclude empty blocking keys. Count postings/block sizes before expanding them. Common names, cities and generic address words require a secondary key or ranked retrieval, not an unbounded Cartesian expansion. Keep the raw word in the record even when excluding it from a particular blocking key.

Start with a bounded query sample against the complete target corpus, with every true target still available. Suggested first benchmark: 10,000 deterministic development-training S1 queries stratified by country/cardinality. Then use 50,000 held-out queries, then the full validation query set. These are proposed sizes, not experiments already run.

For n-gram retrieval, compare `char` and `char_wb` with n-gram ranges such as 3-5. Use a sparse inverted index or a top-k sparse retrieval implementation; do not materialize the complete query-by-target cosine matrix. Set `strip_accents=None` on the primary Unicode-preserving view. Default word tokenizers may split/drop combining marks; use the existing keys with a deliberately chosen tokenizer. [TF-IDF vectorizer documentation](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html)

Sweep per-method k values such as 10, 20, 50 and 100, then measure recall after the final union, deduplication and any cap. Protect complementary retrieval channels when trimming; a name-only rank can remove the only correct address-only candidate. An average of 50 final candidates already gives roughly 86.6 million test pairs; 100 gives roughly 173.3 million.

### B5. Candidate metrics and targets

For each method and union, report:

- Micro link recall: total true links retrieved / all true links.
- Macro link recall over non-singleton S1 entities.
- Complete-entity coverage: non-singletons with every true link retrieved / non-singletons.
- Fraction of queries with zero candidates, split by true singleton/non-singleton.
- Candidate-count p50/p95/p99/max and total distinct pairs.
- Counts before and after block caps and ranking filters.
- Runtime, peak memory, bytes on disk and largest blocks.
- Oracle macro F0.5 if all retrieved true matches were selected and all false ones rejected.

Report all metrics by country, target source, missing-address status, cross-script status and match count. France has no labels, so its candidate sizes and text quality can be measured, but its recall cannot.

Use 99% micro recall and 99.5% as a stretch target during development; these are engineering targets, not guaranteed or competition-imposed thresholds. An aggregate target alone cannot excuse a weak cross-script slice. Choose the final operating point from the measured recall/cost curve, and explain any remaining misses.

Reduction ratio must declare its denominator. Give both `1 - candidates/all_pairs` and `1 - candidates/same_country_pairs` if reporting both; mixing denominators makes results misleading.

### B6. Hard negatives and pair-level EDA

Label a generated training pair positive only if that exact pair exists in the ground truth; otherwise label it negative under the challenge's label contract. A true positive omitted by retrieval remains a retrieval miss, not a negative.

Compare positives against retrieved hard negatives with similar names, shared addresses, conflicting unit numbers, common business names, or transliteration collisions. Keep a small random-negative stratum for context; do not rely on random negatives alone. Track how many negatives are sampled per query and preserve their sampling probabilities for later calibration analysis.

Never inject missed ground-truth pairs into a validation candidate set. If injecting missed positives for later classifier training, mark that augmentation explicitly and report retrieval performance on the unmodified candidates.

Review similarity distributions and class overlap. Include name character similarity, token overlap, rare-token agreement, address similarity, numeric agreement/conflict, script flags and missingness. RapidFuzz `token_set_ratio` can reach 100 when one token set is contained in another, even with extra content, so a score of 100 is not an identity guarantee. [RapidFuzz token-set behavior](https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html)

Manually inspect a bounded, stratified set of 20-30 pairs per major failure type using only provided data. Store IDs, observed text, failure category and proposed fix. Do not look businesses up on the web, and do not relabel official ground truth based solely on subjective plausibility.

## 9. EDA deliverables and decisions they support

| Analysis | Owner | Visual/table | Decision |
|---|---|---|---|
| Country/source composition and train/test shift | A | counts and proportions | France/India workload and evaluation slices |
| Missing addresses by country/source | A | missingness table | fallback name retrieval |
| Script mix and combining-mark incidence | A | counts/examples | transliteration and Unicode tests |
| Length, numeric token and whitespace distributions | A | histograms/quantiles | parser/features; no automatic outlier deletion |
| Normalized collisions in S1 | A + B | group-size histogram and examples | cleaning aggressiveness and split groups |
| Match-count and singleton distribution | B | histogram/table | stratification and metric cases |
| Positive versus hard-negative similarity | B | distributions by slice | feature usefulness and false-merge risks |
| Candidate recall versus number of pairs | B | curve | k/caps/rule selection |
| Cleaning ablations | A + B | before/after recall, collisions, pairs | adopt/reject a rule |
| Full-key overlap across train/test | B | exact counts | leakage/ambiguity investigation, not label copying |

Use a compact set of plots to answer these questions. Broad numeric correlation matrices, PCA of entity IDs, and automatic 'outlier removal' are not useful defaults for this mostly text dataset.

## 10. What can be cleaned away

| Item | Action | Reason |
|---|---|---|
| `__MACOSX/`, `.DS_Store`, `._*` | Exclude from discovery, Git and submission; deletion unnecessary | Archive/OS metadata |
| Empty or repeated whitespace | Normalize in derived text only | Reduces cosmetic differences |
| Punctuation | Preserve raw; convert to boundaries in auxiliary keys | Meaning can survive in raw and structured features |
| Generic words/legal forms | Keep raw; downweight or extract in selected views | Blanket deletion creates collisions |
| Repeated Source 2/3 text with different IDs | Retain every ID | Multiple required matches may share text |
| Unmatched S2/S3 training records | Retain in retrieval corpora | Realistic distractors/hard negatives |
| Missing-address records | Retain, flag, use fallback retrieval | Valid evaluation cases |
| France records | Retain and process | Required unseen country |
| Long/short/noisy text | Flag and inspect | Noise is part of the task |
| Old diagnostic outputs | Exclude from submission; archive once superseded | Avoid confusing versions |

The newly added `.gitignore` excludes metadata, source datasets, environments and generated data. It does not delete files. No source records should be removed merely because they are difficult to match.

## 11. Shared milestones and handoffs

Schedule by completion criteria rather than a fixed calendar. A practical first cycle is five focused work sessions, with full scans running between them; actual duration depends on retrieval experiments and hardware.

| Session | Member A | Member B | Joint checkpoint |
|---|---|---|---|
| 1 | Review full audit; confirm schema and quality flags | Review labels, scorer cases and ambiguity | Agree versions, folder ownership and split protocol |
| 2 | Test multilingual views on representative records | Generate/freeze splits; build R1/R2 baselines | Handoff normalization fixture set and fold manifest |
| 3 | Improve names/addresses only where evidence supports it | Add rare-token/n-gram retrieval and full-corpus query benchmark | Compare recall/cost; inspect misses together |
| 4 | Finalize clean record features and collision report | Build hard negatives, pair EDA and feature schema | Freeze normalization + retrieval versions |
| 5 | Regenerate/reconcile clean data and resource report | Run final candidate evaluation, leakage and export checks | Approve pretraining handoff checklist |

A can start source profiling while B analyzes labels. B can build metric and split tests before rich normalization is ready. B must wait for a versioned normalization contract before treating a candidate benchmark as comparable. A must wait for B's retrieval/error evidence before adopting aggressive cleanup.

Use separate development branches when a Git repository is established, and exchange code/configuration/report summaries rather than multi-gigabyte TSV copies. Shared data files must have identical checksums on both machines. Do not rely on a shared mutable notebook as the source of truth.

For each experiment log `experiment_id`, input hashes, source-code revision, normalization version, split version, candidate version, settings, seed, runtime, memory, per-slice metrics and a one-sentence decision. Both members should be able to reproduce it from command-line scripts.

## 12. Ready-for-training checklist

- [x] All seven source checksums and parse counts recorded for the current audit.
- [x] Every source ID retained in the current Parquet copies; no unexplained row loss.
- [x] Ground-truth integrity and singleton preservation checked.
- [ ] Unicode/name/address rules versioned with multilingual regression fixtures.
- [x] Raw and basic normalized fields retained separately.
- [ ] Frozen S1/family split and target/distractor assignment policy saved.
- [ ] No validation/holdout labels used in learned normalization rules or training negatives.
- [ ] Metric agrees with singleton cases, official example and all-empty baseline.
- [ ] Retrieval measured after every filter and final candidate cap.
- [ ] Hard-negative distributions and false-merge risks inspected.
- [ ] France handled without closed-country assumptions; no unsupported France score claimed.
- [ ] Candidate pair table and feature schema documented, including missing-value semantics.
- [ ] Data leakage fields excluded: IDs, ground-truth counts, labels, fold and ownership metadata.
- [ ] Full run can be reproduced within measured compute/storage budget.
- [ ] Remaining retrieval misses and ambiguous identities recorded.
- [ ] Both members approve the evidence and handoff.

Only then begin supervised model training. The first model should consume the agreed candidate features; training is a later work package. SageMaker setup remains a separate later step, informed by measured RAM, runtime, temporary disk and candidate volume from this phase.

## 13. Challenge-specific guardrails

The official output is one row for every test S1 ID, including empty-match cases. The final package also needs the candidate list actually scored by the matcher. Preserve retrieval provenance now so that file can later be reproduced exactly.

The README/PDF say unknown target IDs are rejected, while comments in the supplied validator say some unknown IDs merely lower the score. Treat this as a documentation inconsistency: generate only valid test S2/S3 IDs and perform your own strict existence checks. Likewise, the candidate-subset check is a validator warning, but the pipeline should enforce it as an invariant. Default validator mode does not check target-ID existence; `--check-ids` enables it.

External business lookup, registries, geocoding, internet augmentation and commercial entity-resolution APIs are prohibited. Researching algorithms/software documentation is different from enriching competition records: the sources below inform implementation only. Any future pretrained model must satisfy the stated MIT/Apache 2.0 and up-to-8B-parameter constraints; audit checkpoint licenses separately from Python-package licenses.

## 14. Sources and reproducibility

Competition rules: local `student_resource/README.md`, the supplied problem-statement PDF, `student_resource/utils/validate_submission.py`, and the organizer's [briefing video](https://d8it4huxumps7.cloudfront.net/files/6ab509c5b7036_ml_challenge_2026_video.mp4). This follow-up uses the written specification as the authority and does not claim a new full audio transcription of the video.

Dataset evidence: `reports/eda/full_audit.json` and accompanying CSVs, generated by `scripts/audit_dataset.py`. Reports distinguish full-data counts from sampled fuzzy similarities and proposed experiments.

Method sources consulted on 25 September 2026: official DuckDB, Unicode, scikit-learn, Splink and RapidFuzz documentation linked in the relevant sections. Suggested team workflow, targets and retrieval settings are recommendations for this dataset, not claims that the cited projects guarantee a competition score.
