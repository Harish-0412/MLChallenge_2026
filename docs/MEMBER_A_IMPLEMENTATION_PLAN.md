# Member A: phase-by-phase implementation plan (feature version `feat_v2_0`)

Prepared 25 September 2026. Companion to [MEMBER_A_DATA_CLEANING.md](MEMBER_A_DATA_CLEANING.md) (what to deliver) and [TEAM_PRETRAINING_PLAN.md](TEAM_PRETRAINING_PLAN.md) (how A and B fit together). Rule-by-rule evidence, example IDs and tests: [cleaning_decisions.md](../reports/eda/cleaning_decisions.md).

This document says **how to build it**, in order, with the measured evidence that ranks each step. **Phases 0-6 are now implemented and verified** (see "Implementation status" below); the code blocks under Phases 7-9 are still reference sketches, and the Phase 5 and 6 sketches were replaced by the implemented code described in their "Implemented" blocks.

---

## Implementation status (26 September 2026)

| Phase | Status | How it was verified |
|---|---|---|
| 0 Baseline, contract, environment | **Done** | 11 baseline tests; seven input SHA-256 values equal the audit (`baseline_hashes.txt`); dependencies pinned in `requirements-features.txt`; contract note written as a **proposal awaiting Member B** (`reports/cleaning/contract_feat_v2_0.md`) |
| 1 Input manifest and guard rails | **Done** | `manifests/input_manifest_v1.json` (SHA-256 `046b2b1d...4ce1`) reconciles 24,229,173 rows across Python strict parse, DuckDB raw parse, Parquet and the audit; rebuild is byte-identical; 36 tests including 9 that sabotage the inputs and require refusal; anomalies explained in `reports/cleaning/input_anomalies.md` |
| 2 Text hygiene and flags | **Done** | Full scan of all 24,229,173 rows, 8/8 checks: v1-key parity Python vs DuckDB (0 differences), every flag equals the audit's independent SQL count, no mark or number lost, no new empty view, every view idempotent, dotted lexicon equals the census; ftfy experiment (`ftfy_experiment.md`) |
| 3 Name features | **Done** | Full scan of all rows (`name_verification.json`): zero structural violations, four counts equal independent SQL, placeholders equal the audit, collision table for every view (`name_view_collisions.csv`); 68 fixtures + mutation tests |
| 4 Scripts and transliteration | **Done; bake-off provisional** | Script bitmask equals the EDA census in all 270 cells; 27 real cross-script true pairs validate the native legal tier (100.0% agreement on 27,230 pairs); 31 fixtures, idempotence property test, mutation tests; CPU bake-off and GPU bake-off (`translit_bakeoff.md`, `neural_bakeoff.md`) - **provisional until Member B freezes a fold** |
| 5 Address features | **Done** | 90 fixtures (14 verbatim true pairs; hand-written expectations), 30 unit/property/mutation tests; the built table passes 15 address-specific independent SQL invariants over all 24,229,173 rows (`D30`-`D44`, part of 74 SQL invariants), a digit-run preservation check and Python recomputation; true-pair agreement and per-rule ablation in `address_pair_agreement.md`: exact token-set agreement 31.1 / 44.5 / 38.4 / 51.8% (S2-India / S2-US / S3-India / S3-US) vs 12.2 / 14.3 / 4.3 / 4.8% for the v1 key; 270-row hand review (`address_extraction_sample.md`) found and fixed four issues |
| 6 Build pipeline and storage | **Done** | `data/features/feat_v2_0`: 24,229,173 rows, 69 columns, 251 ZSTD files, 8.69 GB, built in 1,085 s (22,328 rows/s, 6 workers, worker peak RSS 939 MB). `scripts/verify_features.py`: **120/120 checks pass** (`reports/cleaning/feature_verification_feat_v2_0.json`): file/schema/manifest agreement, content-hash sums equal the input manifest for all six tables, no NULLs, 74 independent SQL invariants, reproduction of 957 cells of the earlier full scans (0 differ), Python recomputation of 21,684 stratified rows over all columns, byte-identical scratch rebuilds with different worker counts. 13 sabotage tests prove the verifier fails when it should |
| 7 Verification and QA gates | **Largely covered** | Gates 1-5 and 8-11 are automated in `verify_features.py`; gates 6-7 (marks/digits kept, idempotence) were verified by the Phase 2/3 full scans and re-checked on the table (`D9`, `D43`, `F3`); gate 12 is partly done (fixtures pass, 270 address rows hand-reviewed) - the per-rule 20-30 example file `rule_review_samples.md` is **not written** |
| 8-9 | Not started | |

The scan tooling lives in `src/cleaning/hygiene_scan.py` and `name_scan.py`, the table verification in `src/cleaning/feature_verify.py`; the full suite is **191 tests, all passing** (`python -m unittest discover -s tests`).

### Deviations from the plan as first written

1. **Manifest location**: `manifests/` (top level, so it is not swallowed by the `data/` ignore rule), not `data/manifest/`.
2. **Lexicon data directory**: `src/cleaning/lexicon_data/` (a directory named `lexicons/` would have shadowed the `lexicons.py` module). Fixtures are JSON Lines, not TSV, because control characters need escapes.
3. **New evidence changed the design** (all in `reports/eda/cleaning_decisions.md`): `M/s` and `Smt` are injected prefixes; accent noise reaches legal words; `d/b/a` markers exist only in Source 3; U+001A is a substituted *apostrophe* as well as a dash (which is why a boundary, not ftfy's deletion, is right); `name_compat_key` (NFKC) differs from the v1 key in 0 rows.
4. **Bugs the verification found and fixed**: a dotted-acronym boundary case (`AL.L.C` -> `AL.LC`); a non-idempotent skeleton (now iterated to a fixed point); a wrong invariant about digit-only names; ordinal indicators `º`/`ª` classified as "Other" instead of Latin (23,690 French addresses; fixed by deriving Latin ranges from the same Unicode tables as the other scripts).
5. **The first Phase 2 scan reported a failure** (hand-summed lexicon counts differed slightly from the census, and one frequent dotted form `P.O.` had not been reviewed); both were fixed in data files and the scan rerun to a full pass. Two overlapping scan jobs briefly wrote to one log; the redundant one was stopped and the results above come from a single clean run.
6. **Git** was not initialised (decision D2 remains the user's call); source revisions will be a source-tree hash in Phase 6.
7. **GPU**: the RTX 3050 cannot accelerate this pipeline (Python, regex and DuckDB are CPU-bound). It is used for one bake-off candidate, in a separate `.venv-gpu` (PyTorch 2.14 cu126, LaBSE Apache-2.0, multilingual-e5-small MIT; ~5 GB downloaded with the user's approval).
8. **Native-script state names come from the unlabeled census, not from labeled pairs.** The plan said "derive from the dev fold"; B has not frozen a fold, so every state form is a curated definition admitted only if the train text shows >= 50 whole-segment occurrences (France: >= 1,000, from unlabeled test text). Labels are used only to *report* agreement.
9. **Phase 5 grew four rules after the first full build** (A-11..A-14 in the decisions log: injected `PO BOX`/`PMB`/`CDP`, injected India `HN n`/`b3`/`Region`/`DIVREPORTINGCIRCLE`, `Ct`/`Hwy`, comma-separated number labels). They came from scanning the census for high-lift tokens and from the hand review of 270 built rows. The table was rebuilt and re-verified as the same `feat_v2_0` (nobody had read the first build). The first build had passed every check of blocks A-E and, run separately, F and G; its full verification run was stopped in F because the recomputation step was too slow (it decoded every column 27 times), which led to the faster two-phase sampling now in `feature_verify.py`.
10. **Verification code is excluded from the source-tree hash** (`feature_verify.py`, `hygiene_scan.py`, `name_scan.py`): checking a table must not invalidate it. I found this the hard way (a first build had to be restarted after adding a verification module changed the hash).
11. **Phase 6 command line differs from the sketch**: `--max-groups N` (sample = first N row groups of each input table) and `--flush-rows`, no `--batch-size`; the unit of work is two consecutive row groups, one part file per country per task, named `part-<table>-<first group>.parquet`. Builds go to `<version>.tmp` and are renamed only on success.
12. **Bugs and rule flaws that verification found (all fixed, all with regression tests)**: a number label separated from its number by a comma (`Plot No, 93`) broke idempotence; zeros were stripped after the noise rules (`B03` vs `b3`); `n` as a number label deleted real unit letters and gave no gain (removed); the plain `suffix` rule would have turned the state code `CT` into `court`; three verifier mistakes (`array_to_string([])` is NULL in DuckDB; a stratum that is genuinely empty in the data; a verifier that decoded every column 27 times).

---

## 0. Summary

**Goal.** Turn the six raw record tables (24,229,173 rows) into a versioned, reproducible Parquet feature table that keeps every raw field and adds several *named views* of each name and address, plus quality flags. Member B consumes these views for retrieval, hard negatives and later pair features.

**What the data says should drive the work** (details in section 2):

1. **Legal-form and `.com` handling is the single biggest name lever** (+18 to +33 pp exact name agreement on true pairs), but it raises Source 1 name-key sharing from 31% to 41%. It must be a gated retrieval/feature view, never an identity key.
2. **State/region canonicalization** is the biggest address lever (+11 to +14 pp on S3), and **abbreviation expansion** adds +12.5 pp on US S2. All address rules together take exact agreement on true pairs from 4-14% to 22-49%.
3. **Cross-script names are 23.4% of India-S2 and 12.5% of India-S3 true links**; the current key scores them with a median similarity of 10. A simple Latin skeleton reaches a median of 85-86 on the name core.
4. **`NA` names are dropped names, not distractors**: 24 of 24 in training are true links. They need an address route.
5. **Mojibake is upstream and shared** between a record and its match, so it barely affects matching (0 pp measured). Treat it as a hygiene flag, not a priority.
6. **ZWNJ splits Indic words into two tokens** (S2 25,643 / S3 14,514 train names).
7. The current v1 key has concrete defects: `L.L.C.` -> `l l c`, `°` vs `º`, apostrophes, `latin_accent_key` unused and slow, no country-scoped legal lexicon.

**Ten phases**, each with an acceptance test:

| Phase | Deliverable | Rough effort (a guess, not measured) |
|---|---|---|
| 0 | Baseline check, contract with B, environment | 0.5 day |
| 1 | Input manifest and ingestion guard rails | 0.5-1 day |
| 2 | Text hygiene layer and flags | 1-1.5 days |
| 3 | Name features (legal form, core, domain, placeholder) | 1.5-2 days |
| 4 | Script census and transliteration bake-off | 1.5-2 days |
| 5 | Address features (segments, canonical views, numbers, states) | 2-3 days |
| 6 | Feature build pipeline and storage | 1.5-2 days |
| 7 | Verification and QA gates | 1 day |
| 8 | Ablation with B: coverage vs collisions, promote/reject | 1-2 days (shared) |
| 9 | Handoff package, resource report, review of B's split and scorer | 0.5-1 day |

### Evidence status (read before trusting any number)

- **Full-data measurements** (every row): pattern counts, last-token tables, state-token tables, throughput. From DuckDB queries over the six Parquet files.
- **Sample measurements** (0.5% positive-pair sample, ~38k pairs): rule lift on *true* pairs, transliteration bake-off. These are exploratory. They show **recall-side** lift only; **precision-side** cost is measured for one view (name core on full S1) and must be measured for all views in Phase 8.
- The prototype used labeled pairs from a sample that predates B's split. It informed *which rules to try*, not lexicon entries or thresholds. All label-derived mappings must be fitted on the frozen development fold (Phase 0 dependency).
- The repository is **not a git repository**, so "source-code revision" in experiment logs must be a source-tree hash (Phase 6). Consider `git init` (decision D2).
- Existing 11 regression tests pass (verified today with `.venv\Scripts\python.exe -m unittest discover -s tests -v`).

---

## 1. Where the project stands

| Asset | Status | Issue found |
|---|---|---|
| `data/interim/*_source*.parquet` | Complete, raw + `name_key` + `address_key`; all six match row counts and hashes | Row order is not file order (`preserve_insertion_order=false`); use `entity_id` sets and order-independent hashes, never row position |
| `scripts/normalization.py` (`nfc_lower_lmn_v1`) | Tested, applied to every row | `L.L.C.` -> `l l c`; `°` (boundary) vs `º` (letter); stray `â`; `lower()` not `casefold()`; ZWNJ becomes a boundary and splits words |
| `latin_accent_key` | Tested, **applied to no row** | 9.5 us/row (calls `unicodedata.name` per character); no ligature table (`œ æ ß ø ł đ`) |
| `entity_f05` in `normalization.py` | Correct on the six documented cases | Scorer lives in the normalizer module; B should move it. Not A's change |
| `scripts/audit_dataset.py` | Full audit, resumable | Python/SQL parity checked only on ~23.7k sampled rows (EDA section 10) |
| `reports/eda/*` | Full audit, script census, positive-pair CSVs | Old exploratory `tmp/profile_dataset.py` counts (e.g. "31.02% repeated names") are superseded by EDA (31.06%) |
| `.venv` | Python 3.12, `duckdb==1.4.3`, `rapidfuzz==3.14.3` only | **No `pyarrow`, no `pandas`**: streaming Parquet batches through Python is impractical until Phase 0 adds `pyarrow` |
| Machine | 12 logical cores, 16 GB RAM, ~114 GB free disk | Plan for ~6 worker processes at well under 1 GB each |

**Reconciling the summary you pasted with the repo.** It is consistent with the EDA on schema, counts, missing addresses and the F0.5 rules. Two corrections for A's work: (a) its "31.02% / 19.95% repeated-name" figures differ slightly from the EDA's full-data counts (31.06% train S1 = 685,397 / 2,206,821; 19.89% train S2); the EDA states that the older exploratory normalizer is superseded, so use the EDA figures; (b) it frames transliteration around Devanagari-Latin; the EDA and today's census show nine Indic scripts, with Devanagari ~55% of non-Latin India targets.

---

## 2. Measured evidence that shapes the phases

Full rule register with example IDs: [cleaning_decisions.md](../reports/eda/cleaning_decisions.md). Highlights:

### 2.1 Name rules, each applied alone (exact agreement on TRUE pairs, Latin-only targets)

| Rule | S2-India | S2-US | S3-India | S3-US |
|---|---:|---:|---:|---:|
| v1 baseline | 18.7 | 26.4 | 18.7 | 25.8 |
| + Latin accent fold | 21.9 | 30.8 | 22.3 | 30.5 |
| + dotted acronym join | 19.2 | 27.9 | 19.3 | 27.1 |
| + legal-form canonicalization | 26.7 | 27.7 | 24.9 | 26.6 |
| + token set sorted | 26.0 | 32.9 | 24.8 | 32.1 |
| + drop bracket text (alone) | 17.5 | 24.5 | 16.9 | 23.5 |
| **+ strip legal forms and `.com`** | **51.6** | **48.6** | **46.4** | **43.8** |
| All name rules -> `name_core` | 56.6 | 56.5 | 51.9 | 51.8 |

Bracket deletion on its own is **harmful**: `(LLC)` in one source must be unwrapped to `LLC`, not removed.

### 2.2 Address rules, each applied alone (non-empty target address)

| Rule | S2-India | S2-US | S3-India | S3-US |
|---|---:|---:|---:|---:|
| v1 baseline | 12.2 | 14.3 | 4.3 | 4.8 |
| + mojibake/control strip | 12.2 | 14.3 | 4.3 | 4.8 |
| + drop `null` / `n/a` tokens | 12.4 | 14.7 | 4.3 | 4.8 |
| + strip leading zeros | 12.7 | 15.3 | 4.4 | 4.8 |
| **+ abbreviation expansion** | 12.2 | **26.8** | 4.3 | 4.8 |
| **+ state code <-> name** | 12.4 | 14.3 | **15.3** | **18.9** |
| + token set sorted | 20.3 | 20.4 | 6.5 | 6.9 |
| **All address rules + token set** | **22.1** | **41.9** | **28.0** | **48.7** |

India stays lower because 24.3% of S2-India and 22.9% of S3-India target addresses contain non-Latin text (native-script state names), S1 carries district segments that S2/S3 drop, and several targets have extra prefixes. Graded similarity (Jaccard >= 0.8 for 52-63% of pairs), not equality, is the right consumer for India addresses.

### 2.3 Cross-script names

- Non-Latin target names: 23.4% of India-S2 true pairs (1,722 of 7,361) and 12.5% of India-S3 (993 of 7,928). Scripts among S2 cross-script pairs: Devanagari 940, Kannada 152, Tamil 147, Telugu 142, Gujarati 113, Bengali 111, Malayalam 70, Gurmukhi 27, Oriya 20.
- Baseline v1-key similarity (RapidFuzz ratio): median **10**.
- `anyascii` (ISC) + a phonetic skeleton on both sides: whole-name median **89-90**; **name core only** (legal suffix removed) median **85-86**, >= 80 for 66-71%, exact skeleton equality for 19-20%.
- `indic-transliteration` (MIT, ITRANS) was worse out of the box (whole-name >= 80: 74% vs 82%) because it keeps inherent schwa vowels (`smArTa`).
- Legal-form words transliterate to near-constant strings (`praivet limited`), which inflates whole-name scores; that is why the core-only figure matters.

### 2.4 Collision cost (full Source 1)

| View | Train S1 rows sharing a key with another S1 row | Largest group | Test S1 | Largest |
|---|---:|---:|---:|---:|
| `name_key` (v1) | 31.1% | 253 | 29.1% | 205 |
| legal-canonical | 32.0% | 253 | 30.1% | 205 |
| `name_core` | **40.9%** | **572** | **39.2%** | **530** |
| `name_core` token set | 41.2% | 572 | 39.5% | 530 |

### 2.4b Prevalence of the noise patterns (full data)

| Pattern | Where | Count / rate |
|---|---|---|
| Domain-form names (`x.com`) | S2 / S3 train | 3.35% / 3.33%; S1: 0 |
| Literal `null` token in address | S2 / S3 train | 131,794 / 130,844 rows; S1: 43 |
| Leading-zero number in address | S2 / S3 / S1 train | 5.54% / 5.24% / 1.13% |
| Double space in name | S2 / S3 train | 554,392 / 575,616; S1: 0 |
| ZWNJ in name | S2 / S3 train | 25,643 / 14,514; S1 and all addresses: 0 |
| Corrupted dash / control chars in address | S1 / S2 / S3 train | 539 / 1,118 / 949 rows |
| `NA`-style name | S2+S3 train / test | 24 (all true links) / 110 |
| US S1 names ending in token `c` (from `L.L.C.`) | train S1 | 45,556 |
| France S3 names ending `s` / `l` (from `S.A.S.` / `S.A.R.L.`) | test S3 | 12,419 / 10,374 |

### 2.5 Throughput measurements

- v1 `comparison_key` on name + address: **10 us/row**.
- Prototype name views (six views): **39-44 us/row** (Source 1).
- Budget for the whole v2 record (all views, flags, addresses, transliteration): guess **120-200 us/row** -> 24.2M rows ~ 50-80 CPU-minutes -> roughly 10-15 minutes wall-clock on 6 processes. **This is an estimate to be replaced by the Phase 6 measurement.**

---

## 3. Architecture decisions

### 3.1 Versioning

- `nfc_lower_lmn_v1` and `scripts/normalization.py` are **frozen**. Tests and the audit depend on them. Do not edit; do not delete.
- New constants: `FEATURE_VERSION = "feat_v2_0"`, `HYGIENE_VERSION = "hyg_v2_0"`. Any rule change after a version is validated creates `feat_v2_1` in a new directory. Never overwrite a validated version.
- Each lexicon file carries its own version string and SHA-256 recorded in the manifest.

### 3.2 Code layout (new; nothing existing is moved)

```text
src/cleaning/
  __init__.py            FEATURE_VERSION, HYGIENE_VERSION
  text_hygiene.py        Unicode/whitespace/mojibake/joiner/accent primitives + flags
  lexicons.py            loads lexicon_data/*.tsv, country scoping, lexicon hashes
  lexicon_data/          (data directory; renamed from lexicons/ to avoid clashing with lexicons.py)
    legal_dotted.tsv     DONE (Phase 2): dotted acronyms that may be joined, with observed counts
    legal_forms.tsv      tier(generic|US|IN|FR), token(s), canonical code          (Phase 3)
    address_abbrev.tsv   tier, abbreviation, expansion, ambiguity rule              (Phase 5)
    states.tsv           country, canonical, code, aliases, native-script variants  (Phase 5)
    generic_tokens_<country>.tsv   frequency-derived, reviewed                       (Phase 3)
  names.py               legal split, core/set/compact views, domain, placeholder
  translit.py            script census, transliteration, skeleton
  addresses.py           segments, canonical views, number spans, states, confidence
  record.py              build_record(name, address, country) -> dict (the single entry point)
  pipeline.py            batch/parallel Parquet I/O                                (Phase 6)
  manifest.py            input manifest, discovery guard, strict parsers            (DONE, Phase 1)
  hygiene_scan.py        full-data scanner used to verify Phase 2                   (DONE)
scripts/
  check_baseline.py      Phase 0 (DONE)
  build_manifest.py      Phase 1 (DONE)
  hygiene_report.py      Phase 2 verification over all rows (DONE)
  build_features.py      Phase 6
  verify_features.py     Phase 7
  view_ablation.py       Phase 8
manifests/               input_manifest_v1.json/.sha256/.run.json  (top level, not under data/, so it is not git-ignored)
tests/
  fixtures/hygiene_fixtures_v2.jsonl   (JSON Lines instead of TSV: control characters need escapes)
  test_manifest.py test_manifest_build.py test_hygiene.py test_hygiene_scan.py   (DONE)
  test_names.py  test_addresses.py  test_translit.py  test_pipeline.py            (later phases)
data/features/feat_v2_0/split=<train|test>/source=<1|2|3>/country=<...>/part-*.parquet
data/features/feat_v2_0/_manifest.json
reports/cleaning/                 QA samples, before/after examples, resource report
```

### 3.3 Engine and dependencies

- **v2 fields are computed in Python**, one entry point `build_record`, so there is a single implementation of every rule (no SQL/Python parity problem). v1 columns are carried through unchanged from the existing Parquet.
- DuckDB stays the tool for **verification, joins and ablations** (fast, SQL, larger-than-memory).
- Add a new requirements file (do not touch `requirements-eda.txt`):

```text
# requirements-features.txt  (pin exact versions after install)
duckdb==1.4.3
rapidfuzz==3.14.3
pyarrow          # Apache-2.0, verified on PyPI: needed for batch Parquet I/O
anyascii         # ISC, verified; transliteration baseline
psutil           # BSD-3-Clause, verified; peak-memory logging
ftfy             # Apache-2.0, verified; EXPERIMENT ONLY on flagged rows (Phase 2)
```

- **Avoid**: `Unidecode` (GPL-2.0-or-later) and `aksharamukha` (AGPL-3.0) for licensing reasons. The challenge's license rule is written about the final model, but the safe default for a code archive that top teams must hand over is permissive licenses only. `indic-transliteration` (MIT) is allowed as a bake-off candidate; `PyICU` (MIT) is excluded unless it installs cleanly on Windows.
- No dependency needs network access at run time. No external lookup of any kind.

### 3.4 Output schema (`feat_v2_0`)

Rules for every column: **strings are never NULL** (empty string = empty view), **lists are never NULL** (empty list), **booleans are never NULL**. Missing information is expressed by explicit flags, never by NULL vs value ambiguity.

| Group | Column | Type | Meaning |
|---|---|---|---|
| Identity | `entity_id` | string | Exact original ID; audit/join key only, **never a model feature** |
| | `id_num` | int64 | Numeric ID suffix (compact join key) |
| | `source` | int8 | 1, 2 or 3 |
| | `split` | string | `train` / `test` |
| | `country` | string | Original label, open vocabulary |
| Raw | `business_name`, `business_address` | string | Byte-identical to input |
| v1 carry-through | `name_key`, `address_key` | string | Unchanged v1 keys |
| Provenance | `feature_version`, `hygiene_version` | string | Constant per build |
| Name hygiene | `name_hyg` | string | v1 rule + repairs (joiners deleted, dotted legal acronyms joined, apostrophes, `°`/`º`) |
| | `name_latin_accent_key` | string | Latin accent fold + ligatures |
| | `name_joiner_key` | string | U+200C/U+200D deleted (not spaced) |
| | `name_compat_key` | string | Optional NFKC view (Phase 8 decides) |
| | `name_apos_join_key` | string | Like `name_hyg` with apostrophes deleted (decision D5; both policies are emitted) |
| Name structure | `legal_form` | string | Canonical code(s), `+`-joined, e.g. `PVT+LTD`, `LLC`, `SARL` |
| | `legal_form_pos` | string | `suffix` / `prefix` / `middle` / `bracket` / `none` |
| | `name_core` | string | Tokens without legal forms and trailing `.com`; falls back to `name_hyg` when empty |
| | `name_core_fallback` | bool | True when the fallback fired |
| | `name_core_fold` | string | Core with Latin accents and ligatures folded (accent noise reaches India/US names) |
| | `name_core_trim` | string | **Experimental**: core without trailing filler words (Center, Services, Summit ...); fitted from unlabeled S1-vs-S2/S3 lift |
| | `name_leading_removed` | string | Leading words removed from the core (`dr`, `mr`, `sri`, `shri`, `smt`, `the`, `m/s`) |
| | `name_alias_marker`, `name_alias_left`, `name_alias_right` | string | `d/b/a`, `a/k/a`, `f/k/a`, `t/a`, `trading as` and the core of each side (Source 3 only in practice) |
| | `name_noise_prefix` | string | Decorative prefix (`**`, `>>`, `..`, `--`, `#`, `@`) |
| | `name_ncore` | int16 | Number of core tokens |
| | `name_core_set` | string | Sorted unique core tokens |
| | `name_core_compact` | string | Core tokens joined without spaces |
| | `name_token_counts` | string | JSON of duplicate-token counts (only tokens with count > 1) |
| | `name_ntokens`, `name_ninformative` | int16 | Total tokens; tokens not legal and not in the generic list |
| | `name_bracket_text` | string | Non-legal bracket content (`India`, `Center`) |
| | `name_is_domain_like`, `name_domain_label` | bool, string | Local parse of `x.com`, `#x`, `--x` |
| Name scripts | `name_scripts` | int32 | Bitmask: Latin, Devanagari, Bengali, Gujarati, Gurmukhi, Oriya, Tamil, Telugu, Kannada, Malayalam, Other |
| | `name_translit` | string | Latin transliteration (auxiliary) |
| | `name_skeleton` | string | Coarse phonetic skeleton of the transliterated **core** (legal forms removed), applied identically to Latin and native names, iterated to a fixed point. Auxiliary, collision-prone: **graded similarity only** |
| Name flags | `name_placeholder_like`, `name_multispace`, `name_has_control`, `name_has_format`, `name_mojibake` | bool | Definitions in Phase 2/3 |
| | `name_repairs` | string | Comma list of repair codes that fired (`zwnj`, `dotted`, `moji`, ...) |
| Address status | `address_missing` | bool | Empty (after strip) address |
| Address views | `address_clean` | string | Hygiene only; preserves every digit and mark |
| | `address_canon` | string | Ordered canonical view (abbreviations, zeros, states, placeholders) |
| | `address_tokset` | string | Sorted unique canonical tokens |
| | `address_segset` | string | Sorted unique canonical segments, joined with a pipe character |
| | `address_segments` | list<string> | Canonical segments, original order |
| Address parts | `address_numbers_raw` | list<string> | Raw number spans as written (`5/105`, `J 105`, `0012`) |
| | `address_numbers_canon` | list<string> | Same spans, leading zeros stripped |
| | `address_number_ctx` | list<string> | 1-2 preceding tokens per span (`h no`, `plot`) |
| | `address_postal_candidates` | list<string> | 5- or 6-digit tokens **as candidates only** |
| | `address_state_canon` | string | Canonical region or `''` |
| | `address_state_conf` | string | `exact` / `alias` / `mapped_native` / `none` |
| | `address_city_candidates` | list<string> | Up to 3 candidate segments; never a single guess |
| | `address_scripts` | int32 | Script bitmask |
| Address flags | `address_mojibake`, `address_has_control`, `address_has_format`, `address_multispace` | bool | Phase 2 (implemented) |
| | `address_null_tokens` (int8), `address_had_leading_zero` | int/bool | Phase 5 |
| | `address_parse_conf` | string | `high` / `medium` / `low` / `missing` (Phase 5 rules) |

About 55 columns. Roughly 24M rows x 55 columns will be several GB in ZSTD Parquet; with ~114 GB free this is fine. **Measure and record the real size in the manifest.**

### 3.5 Storage layout

- Partition by `split / source / country` (15 combinations today; France appears only under `split=test`). Country stays a hive value, so a new country needs no code change.
- Inside a partition, write part files of about 500k rows from parallel workers (India S2 test has 2.3M rows -> ~5 parts). Avoid thousands of tiny files.
- Read in DuckDB with `read_parquet('.../**/*.parquet', hive_partitioning=true)`.

### 3.6 What A may fit from data, and on what (leakage rules)

| Artifact | Fitted on | Notes |
|---|---|---|
| Legal-form lexicon | Manual curation guided by unlabeled token frequency (train text; France from unlabeled test text, documented) | Country-scoped tiers |
| Address abbreviation lexicon | Public suffix conventions + unlabeled frequency | No labels |
| Generic-token / DF tables | Train text (US, India); **unlabeled test-France text** for France, documented as an unsupervised corpus statistic | Must be identical in folds and final inference |
| Native-script state names | **Dev-fold labeled pairs only** (purity >= 0.99, support >= 50) + manual review | Depends on B's frozen split (Phase 0) |
| Transliteration choice | Dev fold | Validation and holdout labels are never used |

Until B freezes the fold, A uses only unlabeled statistics and manual lexicons; label pairs are for inspection.

---

## 4. Phases

Each phase lists: goal, why (evidence), tasks, reference sketch, tests, acceptance, deliverable.

### Phase 0. Baseline, contract with B, environment

**Goal.** Start from a verified baseline and a signed contract, so both members build on identical inputs.

**Tasks.**
1. Run the regression tests (already 11/11 passing today):
   ```powershell
   .venv\Scripts\python.exe -m unittest discover -s tests -v
   ```
2. Recompute SHA-256 of the seven input TSVs and compare with `reports/eda/full_audit.json` `files[]`. Give B the same hashes (exchange as text, not the files).
3. Install the Phase 0 dependencies into the venv:
   ```powershell
   uv pip install --python .venv\Scripts\python.exe pyarrow anyascii psutil ftfy
   .venv\Scripts\python.exe -c "import pyarrow, anyascii, psutil, ftfy; print(pyarrow.__version__)"
   ```
   then freeze exact versions into `requirements-features.txt`.
4. Agree with B, in writing, on:
   - `FEATURE_VERSION` name and output path (`data/features/feat_v2_0/`).
   - The join key (`entity_id`; `id_num` for compact joins) and that **no learned model may see `entity_id`, `id_num`, `source`, `split` or `country` as raw features** (country may be a blocking key, decided by B).
   - **B freezes `fold_manifest.parquet` before A fits any label-derived mapping** (native state names, transliteration choice). Fold assignment by hash of `source1_entity_id` is cheap and should land in the next session.
   - Fixture IDs (start from the IDs in [cleaning_decisions.md](../reports/eda/cleaning_decisions.md)).
5. Decide D1-D4 in section 7.

**Acceptance.** Tests green; both members' hash lists identical; `requirements-features.txt` committed; contract note saved as `reports/cleaning/contract_feat_v2_0.md`.

---

### Phase 1. Input manifest and ingestion guard rails (A1)

**Goal.** A versioned manifest that proves no row disappears and no non-dataset file is ever read.

**Why.** The doc requires an allowlist, exact schemas, strict UTF-8 and reconciliation. The current audit already does most of this; the missing part is a standalone, hash-stamped artifact that the feature build depends on.

**Tasks.** `scripts/build_manifest.py` writes `manifests/input_manifest_v1.json`:
- Seven-file allowlist, explicit paths under `student_resource/dataset/` (no recursive glob), byte size, SHA-256, header, column names, `SOURCE_COLUMNS` / `TRUTH_COLUMNS`.
- **Independent row count** from a streaming Python `csv.reader(delimiter='\t', quotechar='"')`, using the same quote rules as the audit's DuckDB parse (`quote='"'`, strict mode). Require it to equal the DuckDB count. A mismatch means the two parsers disagree about quoting inside text fields; investigate before proceeding.
- Strict UTF-8 check (`open(..., encoding='utf-8', errors='strict')`), BOM handling (audit already uses `utf-8-sig` for headers).
- Per file: row count, distinct ID count, prefix check, per-country counts (matches `file_country_profile.csv`).
- Cross-check against v1 Parquet: `count(*)` and order-independent `sum(hash(entity_id, business_name, business_address, country))`.
- A `discovery_guard()` function that raises if a path contains `__MACOSX`, `.DS_Store`, `._`, `.venv`, `reports`, `data`.

**Tests.** `test_pipeline.py::test_allowlist_rejects_metadata` (feeds `._test_source1.tsv`), `::test_manifest_row_counts_match_audit`.

**Acceptance.** Counts match `full_audit.json` exactly (24,229,173 source rows; 2,206,821 label rows); manifest hash (SHA-256 of the manifest file) is what all later outputs record. B reproduces counts from the manifest alone.

**Deliverable.** `input_manifest_v1.json` + a one-paragraph explanation per anomaly (the anomalies are the ones in EDA sections 2-4: control/format characters, `NA` names, repeated names, France S1 ambiguity).

---

### Phase 2. Text hygiene layer and flags (A2)

**Goal.** One tested module of Unicode primitives, used by every name and address view. Raw text is never modified.

**Why (measured).** ZWNJ splits Indic words (N-12); dotted legal acronyms are split (N-03); accent noise appears in India/US names (N-05); `°`/`º` and `’` are inconsistent (A-09); corrupted dashes leave a stray `â` token (A-01).

**Primitives.**

| Function | Behaviour | Notes |
|---|---|---|
| `nfc(s)` | NFC | Same as v1 |
| `remove_joiners(s)` | Delete U+200C and U+200D (no replacement) | For `name_joiner_key`; also applied before transliteration |
| `fold_latin(s)` | NFD, drop marks whose base is Latin (`ord < 0x250`), re-NFC, then ligature table | **No `unicodedata.name()` call**; Indic marks untouched |
| `repair_mojibake(s)` | Replace `[Â â Ã]? [U+0080-U+009F U+001A]+` by a single space; return `(text, fired)` | Flag first, repair only in derived views |
| `norm_punct(s)` | `’ ‘` -> `'`; `° º` after `n`/`N` -> `no`; en/em dash -> `-` | Small explicit table |
| `join_dotted_legal(s, lex)` | Collapse `(?:[A-Za-z]\.){2,}` **only if the collapsed form is in the legal lexicon** | `J. R. Smith` unchanged |
| `collapse_ws(s)` | Whitespace runs -> one space; returns `had_multispace` | |
| `lmn_key(s)` | The v1 rule (letters, marks, numbers; others -> boundary) | Kept identical to `comparison_key` |

**Reference sketch** (`text_hygiene.py`; validated logic from the prototype):

```python
import re, unicodedata

MOJIBAKE_RE = re.compile('[ÂâÃ]?[\u0080-\u009f\u001a]+')
JOINERS = str.maketrans('', '', '‌‍')
LIGATURES = str.maketrans({'œ': 'oe', 'Œ': 'OE', 'æ': 'ae', 'Æ': 'AE',
                           'ß': 'ss', 'ø': 'o', 'Ø': 'O', 'ł': 'l', 'Ł': 'L', 'đ': 'd', 'Đ': 'D'})
DOTTED_RE = re.compile(r'(?<![A-Za-z])(?:[A-Za-z]\.){2,}')

def fold_latin(text: str) -> str:
    out, latin = [], False
    for ch in unicodedata.normalize('NFD', text):
        if unicodedata.category(ch)[0] == 'M':
            if not latin:
                out.append(ch)              # keep Indic and other non-Latin marks
        else:
            latin = ord(ch) < 0x250 and ch.isalpha()
            out.append(ch)
    return unicodedata.normalize('NFC', ''.join(out)).translate(LIGATURES)

def repair_mojibake(text: str):
    fixed, n = MOJIBAKE_RE.subn(' ', text)
    return fixed, n > 0

def join_dotted_legal(text: str, legal_dotted: frozenset) -> str:
    def repl(m):
        joined = m.group(0).replace('.', '')
        return joined if joined.lower() in legal_dotted else m.group(0)
    return DOTTED_RE.sub(repl, text)
```

**Flags** (all boolean, computed on raw text): `has_control` (`Cc` except tab), `has_format` (`Cf`), `mojibake` (pattern above or U+0080-U+009F or U+001A), `multispace` (`\s{2,}`), `repairs` (codes that fired).

**ftfy experiment (bounded, 0.5 day, last in this phase).** Run `ftfy.fix_text` on the ~1,100 flagged S2 addresses and compare with `repair_mojibake`. Record which one fires, which changes the raw string and whether French accents survive. **Do not enable ftfy in the pipeline** unless it repairs a pattern the rule cannot; the measured impact of this whole rule family is 0 pp on exact agreement, so keep the effort proportional.

**Tests** (`test_hygiene.py`), all from real strings in the register:
- `fold_latin('École')` == `'Ecole'`; `fold_latin('आदित्य')` unchanged; `fold_latin('Cœur')` == `'Coeur'`.
- `remove_joiners` on the Kannada name of S2-100080376 -> `lmn_key` yields **one** token where v1 yields two.
- `join_dotted_legal('Bison  L.L.C.')` -> `Bison  LLC`; `'J. R. Smith'` unchanged; `'L.L.P.'` -> `LLP`.
- Mojibake: an S2-102464820-style address gets the stray `â` removed; flag set; raw unchanged.
- Idempotence over 100k sampled real strings for every view.
- No nonempty name becomes empty unless it consisted only of format/control characters (record those rows).

**Acceptance.** Fixtures pass; per-primitive before/after counts of changed rows saved to `reports/cleaning/hygiene_change_counts.csv`; no `M` or `N` code point is lost from `name_hyg` or `address_clean` relative to NFC raw (property test on a 1M-row sample).

---

### Phase 3. Name features (A3)

**Goal.** `legal_form`, `name_core` and companions, computed with country-scoped lexicons.

**Why (measured).** Legal form is the largest name lever (+18 to +33 pp); bracket handling has a trap (N-07); `name_core` raises S1 name sharing to ~41% (X-01); `NA` names are true links (N-10).

**Step 3.1 Build the lexicons (data-guided, manually reviewed).**
- Rank the last and first tokens of each country's names in S1, S2 and S3 (queries as in section 2), plus tokens with high S2/S3-over-S1 excess frequency.
- Curate three tiers into `lexicons/legal_forms.tsv`:
  - `generic`: `ltd, inc, corp, corporation, co, company, llc, llp, lp, incorporated, limited`
  - `US`: `pllc, pc, pa, plc`
  - `IN`: `pvt, private, limited` and multiword `private limited`, `pvt ltd`
  - `FR`: `sarl, sas, sasu, eurl, sa, sci, ei, snc, cie` (observed in test France text)
- Country scoping rule: `lexicon_for(country)` returns `generic` plus that country's tier; **an unknown country gets `generic` only**, so a new country never breaks the build.
- Words that are also ordinary names (`private`, `sci`, `pc`, `sa`, `co`) must be covered by a country-scoping fixture (e.g. `Private Care Inc` in the US keeps `private`; `Sciences` never loses `sci` because matching is by whole token).
- Save the frequency evidence beside each lexicon entry (`observed_count`, `source`).

**Step 3.2 Extraction algorithm** (`names.py`; pseudocode, the helpers are the rules listed below it).
```python
def build_name_views(raw: str, country: str, lex) -> dict:
    text = repair_pipeline(raw)                        # joiners, dotted legal, punct (Phase 2)
    text, bracket_texts = unwrap_or_extract_brackets(text, lex)   # (LLC)->LLC ; (India)-> bracket_text
    tokens = lmn_key(text).split()                     # Latin accent fold is a separate view
    tokens, legal = extract_legal(tokens, lex)         # multiword first, then single tokens anywhere
    core = drop_trailing_com([t for t in tokens if t not in GENERIC_STOP])   # the/and/of
    if not core: core, fallback = full_tokens, True    # never an empty key
    return {...}                                       # name_core, set, compact, legal_form, pos, counts
```
Rules:
- Bracket handling: unwrap when the content is a legal form or generic word; otherwise move to `name_bracket_text` and exclude from `name_core` **only after** legal extraction (measured: dropping brackets alone lowers agreement by 1.2-2.3 pp).
- Legal tokens are stripped **anywhere in the name** for `name_core` (measured; covers moved suffixes like `LLC TBN Innovative Fund`) but their canonical code and position are stored in `legal_form` / `legal_form_pos`, so the information is not lost.
- Keep duplicate-token counts (`ANIMAL ANIMAL WELFARE`) in `name_token_counts`; `name_core_set` deliberately hides them.
- Generic business nouns (`center`, `services`, `partners`, `group`, `holdings`) are **not deleted**; they feed `name_ninformative` and downstream low-weight features.
- Domain-like: `^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$` -> `name_is_domain_like`; `name_domain_label` drops `.com`, leading `#`, leading `--`. Local text only.
- `name_placeholder_like`: whole trimmed name lower-cased in `{na, n/a, null, none, nan, unknown, -}`. Keep the string. Add nothing else (do not flag every 2-letter name).
- `name_ninformative`: tokens neither legal nor in the generic list for that country (generic list = top-DF tokens, reviewed; fitted per section 3.6).
- Preserve both order-preserving (`name_core`) and order-insensitive (`name_core_set`) views.

**Tests** (`test_names.py`, from register IDs): `Sun Industries LLP` vs `Sun Industries L.L.P.`; `Bison LLC` vs `Bison  L.L.C.`; `TBN Innovative Fund LLC` vs `LLC TBN Innovative Fund`; `XKB Space L.L.C.` vs `XKB (SPACE)`; `Global Classic Southwest, LLC` vs `globalclassicsouthwest.com` (compact/domain); `Mcube (India) Apparels` vs `Mcube-(India) Apparels`; `NA`/`Na`/`NAN` flagged and `Nam`/`Nanda` not; French `Lille Club SAS` legal = `SAS`; `Private Care Inc` (US) keeps `private`; an all-legal name (`LLC`) triggers the fallback and never yields an empty core.

**Acceptance.**
- Fixtures pass; no nonempty name has an empty `name_core` (fallback covers it; count fallbacks and review a sample).
- `name_core` agreement on the 0.5% sample reproduces the prototype range (>= ~50% on the four groups) as a regression guard, **not** as a validation result.
- Collision table for every name view over full S1 (train and test) saved to `reports/cleaning/name_view_collisions.csv` (the prototype figures are in section 2.4).

**Deliverable.** Name-feature columns in the feature table, lexicon files with hashes, documented rules in `cleaning_decisions.md`.

---

**Implemented (26 Sep).** Code: `src/cleaning/names.py`, `lexicons.py`, `lexicon_data/{legal_forms,name_noise_tokens,generic_tokens,appended_noise,placeholders,country_tiers}.tsv`, built by `scripts/build_name_lexicons.py` from `scripts/name_token_census.py` (unlabeled). Evidence and verification: `name_verification.json`, `name_view_collisions.csv`, `name_pair_agreement.md`, `name_examples.md`.

- Exact agreement of name views on true pairs (Latin targets; 0.5% sample; recall side only): v1 key 18.7 / 26.4 / 18.7 / 25.8% (S2-India / S2-US / S3-India / S3-US) -> `name_core` 59.5 / 53.1 / 54.2 / 48.2%; any of the four core views 68.9 / 65.5 / 63.9 / 60.2%; plus the alias part 66.8 / 63.7% on S3.
- Decided by data: brackets stay **inline** (dropping them costs 1.4-1.5 points in the US); the trailing-filler trim is **experimental** (+0.5 to +2.0 points); legal words are matched accent-folded; `M/s` is detected from the raw slash form so initials such as `M S Patel` are untouched.
- Country scoping is enforced and tested (`private`: India only; `sci`, `sarl`, ...: France only; unknown country: generic + native tiers only).
- The lexicons validate on load (no duplicate token, no token with two codes, no code with two ranks, NFC only), and a failing lexicon aborts the run.

### Phase 4. Scripts and transliteration (A2/A3)

**Goal.** A defensible Latin auxiliary view for the nine Indic scripts, chosen by a bake-off on the dev fold.

**Why (measured).** Cross-script pairs are 23.4% / 12.5% of India true links; baseline similarity median is 10; a skeleton reaches 85-86 on the core.

**Step 4.1 Script census function.** Bitmask by code-point ranges (Devanagari 0900-097F, Bengali 0980-09FF, Gurmukhi 0A00-0A7F, Gujarati 0A80-0AFF, Oriya 0B00-0B7F, Tamil 0B80-0BFF, Telugu 0C00-0C7F, Kannada 0C80-0CFF, Malayalam 0D00-0D7F, Latin < 0x250, Other). Script is not language: never name the column `language`.

**Step 4.2 Transliteration pipeline.**
1. `remove_joiners` first.
2. Transliterate **per script run**: leave Latin runs untouched (mixed names such as `স্টার Global Private Limited` exist).
3. Baseline engine: `anyascii` (measured winner out of the box).
4. `name_skeleton` (apply the **same function to both sides**, including S1's original Latin): lower-case; `ph->f`; `sh->s`; `ch->c`; `kh/gh/th/dh/bh/jh` -> plain consonant; `w->v`; `z->j`; `q->k`; `x->ks`; `y->i`; collapse doubled letters; keep each word's first letter and drop later vowels.
5. **Legal words in native script.** Learn a per-script map from native legal strings to canonical codes (e.g. `प्राइवेट लिमिटेड`, `ప్రైవేట్ లిమిటెడ్`, `প্রাইভেট লিমিটেড`, `प्रा. लि.`) by counting the most frequent trailing token pairs per script in S2/S3 (unlabeled) and confirming on dev-fold pairs. Map them to `legal_form` so `name_core` works for native-script names too.

**Step 4.3 Bake-off (dev fold, after B freezes it).**
Candidates: `anyascii`; `indic-transliteration` (ITRANS, plus HK/IAST variants); optionally a data-driven character map learned from dev-fold pairs; PyICU only if it installs cleanly.
Measure per script and overall, on **name core**:
- RapidFuzz ratio distribution (p10/p50/p90, share >= 80, share exactly equal skeleton),
- **collision rate** of the skeleton in S1 (distinct S1 per skeleton key, largest group),
- runtime per name.
Decision rule (proposed, a team choice): pick the engine with the best share >= 80 on core **per script**, break ties by lower collision rate and speed; allow a different engine per script if one clearly wins. Record the decision in `cleaning_decisions.md`.

**Guardrails.** The skeleton removes vowels, so it collides; it is an auxiliary retrieval/feature view, never a sole key. Do not transliterate in place. Test with actual labeled pairs from **every** observed script (fixtures: S1-737170761 -> S2-540633362 Telugu; S1-809824196 -> S2-840805166 and S1-477898461 -> S3-352574101 Bengali; add one pair per remaining script from the dev fold).

**Acceptance.** Per-script report saved; fixtures for all nine scripts pass; runtime per name recorded; chosen engine and its license recorded.

---

**Implemented (26 Sep).** Code: `src/cleaning/translit.py`, `script_ranges.py` (generated from DuckDB's Unicode tables by `scripts/gen_script_ranges.py`), the native tier of `legal_forms.tsv` (33 tokens, 3-5 per script, each asserted to occur in >= 5% of its script's names), `scripts/native_legal_census.py`, `scripts/translit_bakeoff.py`, `scripts/neural_bakeoff.py`.

- **Script census**: the Python bitmask equals the EDA's DuckDB census in all 270 cells (9 scripts x name/address x country x file); Arabic, Cyrillic and Han never occur.
- **Native legal words**: `Limited` ends 69-83% of native-script names, `Private` is second-to-last in 57-72%, `LLP` ends ~5.5%; Devanagari/Gurmukhi/Gujarati add `प्रा` + `लि` (Pvt. Ltd.) in the same 13.0% of names. Validated against ground truth: **the legal-form code of the native target equals the Latin reference's on 100.0% of 27,230 cross-script true pairs**.
- **CPU bake-off** (27,230 pairs, provisional 5% sample): v1-key similarity median 10 -> skeleton 92.3, 93.6% of pairs >= 80 (base skeleton 69.8%). All engines tie once the coarse skeleton is used (`anyascii` 93.6%, ITRANS 93.8%, IAST 93.9%, HK 90.8%); `anyascii` is 9-15x faster, ISC-licensed and needs no extra dependency, so it is the engine. Skeleton-equality is **very ambiguous** (an exact hit shares its key with a median of 60 S1 names, p95 144; 9.9% of hits are unique), so it is a graded-similarity view.
- **GPU bake-off** (RTX 3050 6GB; 10,000 queries ranked among 479,954 unique India S1 names): graded skeleton recall@10/@100 = 82.8% / 95.9%; LaBSE 78.8% / 89.7%; multilingual-e5-small 49.6% / 67.0%. The union of the top-10 lists of skeleton and LaBSE reaches **93.6%** (98.7% at 100 each), so LaBSE is a useful *complementary* retrieval channel; e5-small is not. Tamil is the weakest script for both.
- Remaining before this is final: repeat both bake-offs on Member B's development fold (`--fold-manifest`); B decides in Phase 8 which of `name_core`, `name_core_trim`, `name_skeleton` become retrieval channels.


### Phase 5. Address features (A4)

**Goal.** Preserve everything, add canonical views, structured pieces and honest confidence.

**Why (measured).** Combined address rules lift true-pair exact agreement to 22-49%; state canonicalization and abbreviation expansion carry most of it; native-script state names explain much of what remains for India.

**Step 5.1 Hygiene view `address_clean`.** NFC, whitespace collapse, punctuation normalization; **every digit and mark preserved**. This is the auditable primary view.

**Step 5.2 Canonical segments** (`addresses.py`):
```python
def canon_segments(raw: str, country: str, lex) -> list[str]:
    text = fold_latin(repair_mojibake(raw)[0])
    out = []
    for seg in text.split(','):
        toks = lmn_key(seg).split()
        toks = [t for t in toks if t not in PLACEHOLDER_TOKENS]         # null, n/a, none, nan
        toks = [strip_zeros(t) if t.isdigit() else t for t in toks]     # '00936' -> '936' (raw kept elsewhere)
        toks = expand_abbrev(toks, lex.abbrev_for(country))             # 'st','mt' only at segment end
        seg_txt = ' '.join(toks)
        seg_txt = lex.state_alias.get((country, seg_txt), seg_txt)      # NY->new york, MH->maharashtra, Keralam->kerala
        if seg_txt: out.append(seg_txt)
    return out
```
Views: `address_canon` (ordered join), `address_tokset` (sorted unique tokens), `address_segset` (sorted unique segments), `address_segments` (list).

**Step 5.3 Lexicons.**
- **Abbreviations**: USPS street-suffix conventions (`st, ave, blvd, dr, rd, ln, ct, cir, pl, hwy, pkwy, ter, trl, sq, apt, ste, fl, flr, bldg`) plus India (`nr, opp, ngr->nagar, dist/distt->district, vill->village, sec->sector, chs, blk->block, po`) and France (`r.->rue, av.->avenue, bd->boulevard, pl.->place, imp.->impasse, all.->allée, ch.->chemin`; `st/ste` = **saint**, not street). Each entry carries an ambiguity rule; `st`/`mt` in US expand only at segment end.
- **States**: US 50 + DC (code <-> name); India 36 states/UTs with codes (`MH DL UP KA TN WB GJ TG HR RJ KL ...`) and aliases (`Keralam`, `Orissa`, `Pondicherry`, `Uttaranchal`); France regions (`Hauts-de-France`, `Nouvelle-Aquitaine`, `Pays de la Loire`) and observed départements (`Nord`, `Gironde`, `Loire-Atlantique`, ...) as **region hints, not filters**.
- **Native-script state names**: derive from the dev fold. For each true pair, take S1's state segment (India S1 ends with the English state), collect the target's non-Latin segments, and accept a mapping when purity >= 0.99 and support >= 50; review manually. Store `address_state_conf = mapped_native`.
- France's mapping cannot be validated (no labels): mark `address_state_conf` accordingly and report France coverage separately.

**Step 5.4 Number spans** (raw + canon + context). Draft regex, to be refined against fixtures:
```python
NUM_SPAN = re.compile(r"""(?<![\w])
    (?:[A-Za-z]{1,2}[ -]?)?               # optional letter prefix: J 105, C-251, Rz-99
    \d+(?:[-/]\d+)*                        # 5, 5-105, 5/105, 3-277/1
    [A-Za-z]?                              # 12A
    (?:\s(?:bis|ter|quater))?              # 5 bis (French)
    (?![\w])""", re.X)
```
Store `raw` exactly, `canon` = zeros stripped per numeric component, and `ctx` = preceding 1-2 tokens (`h no`, `shop no`, `door no`, `plot`). **Do not assign meaning** (house vs unit vs postal). Numeric agreement is scored by B, label-agnostically (measured: `Shop No 377` vs `Door No 377`; `Khasra No 416` vs `Door No 416`).
`5-105` must not equal `5105`; `0012` keeps its raw form; `J 105` vs `J 5-105` remain distinct spans.

**Step 5.5 Postal candidates.** Tokens of 5 or 6 digits, tagged only as *candidates*. Do not call them confirmed PIN/ZIP codes.

**Step 5.6 Missingness and confidence.**
- `address_missing` = empty after strip. All address views empty; lists empty. Never fill from other rows, IDs, labels or any lookup.
- `address_parse_conf`: `missing` (empty), `low` (no state and no number), `medium` (state or number but not both), `high` (state canonical and >= 1 number span). This is a descriptor for B, **not a filter**.

**Tests** (`test_addresses.py`, real fixtures from the register):
`22 Champlain Avenue` vs `022 CHAMPLAIN AVE` (zero + abbreviation); `936` vs `00936, null, Topsia, WB` (zero + null + state code); `Tulsa, OK` vs `Tulsa, Oklahoma`; `Lysander, NY` vs `Baldwinsville, New York` (state equal even though city differs); permuted segments give equal `address_segset`; `Main St` -> `main street` but `St Louis` unchanged; number fixtures `5 bis`, `5/105`, `5-105`, `J 105`, `0012`, `12A`, `224 1/2 48 St`, `3-277/1` vs `277/1`; French `N°5` == `Nº5`; empty address -> `address_missing`, all views empty.

**Acceptance.**
- All valid rows remain; every proposed hard filter (if B wants one) has measured positive-link losses attached.
- Extraction-quality sample: 30 rows per country x source with raw and each view, reviewed by A, saved to `reports/cleaning/address_extraction_sample.md`.
- Confidence definitions written and used consistently.
- True-pair agreement on the 0.5% sample reproduces the prototype range as a **regression guard**.

**Deliverable.** Address feature columns, lexicons with hashes, extraction-quality sample, documented confidence rules.

---

**Implemented (26 Sep).** Code: `src/cleaning/addresses.py` (`build_address_features(raw, country, cleaned=None)`), `lexicons.py` (address tiers), `lexicon_data/{states,address_abbrev,address_noise}.tsv` (every row carries its measured evidence), `scripts/address_token_census.py`, `build_address_lexicons.py`, `address_eval_pairs.py`, `address_extraction_sample.py`.

- **Columns** (17): `address_canon`, `_tokset`, `_segset`, `_segments`, `_nsegments`, `_numbers_raw/_canon`, `_number_ctx`, `_postal_candidates`, `_state_canon`, `_state_conf`, `_city_candidates`, `_scripts`, `_null_tokens`, `_had_leading_zero`, `_extras`, `_parse_conf` (meaning: contract section 3c). Order of operations per comma segment: tokenise -> strip zeros -> junk-segment check -> remove injected components -> drop number labels (also across a comma) -> expand abbreviations -> state lookup.
- **Lexicons are evidence-first**: US 45 state codes + 46 names; India 16 states x (code, name, native form) + 2 aliases; France 3 regions + 4 départements; 15 US (incl. `ct`, `hwy`) + 10 France abbreviations; junk and injected components per country. An entry is written only if the unlabeled census supports it (`build_address_lexicons.py` prints what it excluded, e.g. `sq`, five US states that never occur, all France départements below 1,000 observations).
- **Rules beyond the plan** (from the census and the hand review): A-11 (US injected components), A-12 (India injected components), A-13 (`suffix_multi`), A-14 (comma-separated labels); measured ablation on 14,669 India and 21,793 US true pairs: `+1.1..+1.2 pp` (`ct`/`hwy`), `+1.2..+1.7 pp` (India components), `+1.9..+2.0 pp` (US components), 0.0 pp (comma labels). Not shipped: `n` as a label, trailing `city`/`county`/`township` (candidate for `feat_v2_1`).
- **Verified**: 90 fixtures, mutation tests for every rule, a real-data fixed-point test (canon of canon equals canon on 30k+ rows), and on the built table 15 independent SQL restatements over all rows (segment/canon/set consistency, the `parse_conf` rule, missing-address emptiness, postal and city-candidate shape, per-country removed-component grammar, leading-zero flag, no digit run dropped or invented).
- **Findings for B**: state disagreement is not a veto (all 1.3% India disagreements are `Telangana` vs `Andhra Pradesh`); numbers disagree in 10.7-13.8% of true pairs that have numbers on both sides; `NO119`-style spans are not extracted (known limit); France has no region in 29.6% of rows (2.5% of them have no address at all).

---

### Phase 6. Build pipeline and storage (A5)

**Goal.** One command reproduces the entire feature table from the input manifest, deterministically, with recorded cost.

**Design.**
- Task unit = (input Parquet file, row-group range). Worker processes (`ProcessPoolExecutor`, start with 4, tune to 6) read with `pyarrow.parquet.ParquetFile.iter_batches(batch_size=50_000, columns=[...])`, run `build_record` per row, and write one Parquet part file (ZSTD) per task under the partition directory. Start with 50k-row batches and adjust from measured RSS; **this batch size is a starting point, not a tested guarantee**.
- Per-worker LRU cache keyed on raw name and on raw address (up to 17-31% of names repeat within a source by normalized key), sized in entries, not bytes.
- Determinism: no reliance on `hash()` or set iteration order (always sort); set `PYTHONHASHSEED=0` as belt and braces; output order is irrelevant because every check is order-independent.
- Never write into an existing validated version directory; refuse if `_manifest.json` exists unless `--force-new-version` creates a new directory.
- Reference skeleton:
  ```python
  def process_task(task):
      pf = pq.ParquetFile(task.src)
      writer = None
      for batch in pf.iter_batches(batch_size=50_000, row_groups=task.groups,
                                   columns=['entity_id','business_name','business_address','country','name_key','address_key']):
          rows = [build_record(*r) for r in zip(*[batch.column(c).to_pylist() for c in COLS])]
          table = pa.Table.from_pylist(rows, schema=SCHEMA)     # explicit schema, no inference
          writer = writer or pq.ParquetWriter(task.dst, SCHEMA, compression='zstd')
          writer.write_table(table)
      writer and writer.close()
      return task.stats            # rows, id-hash sum, seconds, peak_rss_mb
  ```

**Sidecar `_manifest.json`.** `feature_version`, `hygiene_version`, input manifest SHA-256, **source-tree hash** (SHA-256 over `src/cleaning/**` and lexicon files, because there is no git revision), lexicon file hashes, library versions (`python`, `duckdb`, `pyarrow`, `anyascii`, `rapidfuzz`), per-partition row counts and order-independent hash sums, wall-clock time, per-worker peak RSS (psutil), total bytes on disk, command line.

**Commands.**
```powershell
.venv\Scripts\python.exe scripts\build_manifest.py
.venv\Scripts\python.exe scripts\build_features.py --version feat_v2_0 --workers 6
.venv\Scripts\python.exe scripts\verify_features.py --version feat_v2_0
```
Try `--max-groups 1 --version feat_v2_0_sample` first (about 40 s) to validate schema, throughput and memory, then run the full build.

**Acceptance.** Full build completes; the manifest records runtime, peak memory and disk size (these become the SageMaker sizing inputs); B can read any partition with DuckDB using only the documented command; no interactive state is needed.

**Implemented (26 Sep).** Code: `src/cleaning/record.py` (69 columns, explicit non-nullable Arrow schema, per-worker LRU caches on (name, country) and (address, country)), `pipeline.py` (row-group tasks, per-country ZSTD part files, `.tmp` then atomic rename, refuse-to-overwrite, input-manifest guard, source-tree and lexicon hashes), `feature_verify.py`, `scripts/build_features.py`, `scripts/verify_features.py`.

| Measured (final build of `feat_v2_0`) | Value |
|---|---|
| Rows / columns / files / partitions | 24,229,173 / 69 / 251 / 15 |
| Disk | 8,689,710,362 bytes (8.1 GiB); about 359 bytes per row; by compressed column size the raw fields and v1 keys are 20.5%, the five name hygiene views 18.0% and the five address canonical views 31.2% (each of the largest ones is 6-7%), so dropping views would be the way to shrink it |
| Wall time, 6 workers | 1,085 s (18.1 min); 22,328 rows/s; 6,359 CPU-seconds in workers (about 6 cores busy); the sample build (first row group of each table, 737,280 rows) takes 32-40 s |
| Peak memory | 939 MB per worker (RSS), so 6 workers stay under 6 GB on the 16 GB machine; the whole pipeline is CPU-bound Python, no GPU |
| Determinism | Two scratch rebuilds with 2 and 5 workers are **byte-identical** file by file; a rebuild with another flush size (different row groups) has identical logical content; every rebuilt row equals the stored row |
| Reading | `duckdb.read_parquet('data/features/feat_v2_0/**/*.parquet', hive_partitioning=true)` (README) |

Sizing for SageMaker (estimate, not measured there): the build needs about 8-9 GB disk for the table, 1 GB RAM per worker, and about 6,400 CPU-seconds, i.e. roughly 18 minutes on 6 vCPUs or 9 minutes on 12.

**What the verification found.** Nothing was wrong with the data path (content hashes, raw fields and v1 keys equal the inputs in all six tables). It found: a verifier NULL trap (`array_to_string([])`), two address rule flaws (comma-separated labels, zero stripping after the noise rules) and the need for four extra address rules (see deviations 9 and 12).

---

### Phase 7. Verification and QA gates

Run `scripts/verify_features.py`; every check must pass before handoff.

| # | Check | Method |
|---|---|---|
| 1 | Row counts per split/source/country equal v1 and `full_audit.json` | DuckDB `count(*)` |
| 2 | ID sets identical (both anti-joins empty) and no duplicate `entity_id` | DuckDB |
| 3 | Raw fields byte-identical | order-independent `sum(hash(entity_id, business_name, business_address, country))` equals v1 |
| 4 | v1 keys carried unchanged; `comparison_key(raw) == name_key` / `address_key` | **1M sampled rows** (up from 23.7k in the audit) |
| 5 | Nonempty name -> nonempty `name_hyg` and `name_core`; empty results listed with reasons | SQL + review file |
| 6 | No `M`/`N` code point lost from `name_hyg` / `address_clean` vs NFC raw | property test on 1M sample |
| 7 | Idempotence of every string view | 1M sample |
| 8 | Null semantics: no NULL in any column | `count_if(col IS NULL)` = 0 |
| 9 | Flags equal an independent SQL recomputation (`address_missing`, `name_placeholder_like`, `name_has_control`, `name_multispace`) | DuckDB regex |
| 10 | France present in `split=test`; every country in the input appears in output | group-by |
| 11 | Determinism: two builds give equal aggregate hashes on all view columns | rebuild a sample |
| 12 | Fixtures pass; 20-30 examples per rule reviewed by hand | `reports/cleaning/rule_review_samples.md` |

**Handoff QA artifacts:** before/after examples per rule, change counts per rule, list of any emptied views with reasons.

---

### Phase 8. Ablation with B: coverage versus collisions

**Goal.** Promote only rules whose recall gain is worth their ambiguity cost, measured on the **frozen dev fold**.

**For every view `V` (each `*_key`, `name_core`, `name_core_set`, `name_core_compact`, `name_skeleton`, `address_canon`, `address_tokset`, `address_segset`) report:**
1. **New true-link coverage:** true links retrieved by `country + V equality` that no existing channel retrieved.
2. **Collision cost:** distinct S1 per key, target rows per key, largest block, share of S1 rows in a shared key.
3. **Precision proxy:** among pairs retrieved by `country + V equality`, the fraction that are true.
4. **Slice breakdown:** country, target source, cross-script, missing-address, match count, `name_placeholder_like`.

**SQL sketch** (`scripts/view_ablation.py`; blocks counted before expanding pairs; `fold` comes from a join with B's `fold_manifest.parquet`, it is not a feature column):
```sql
WITH q AS (SELECT entity_id s1, country, {view} k FROM feat WHERE source=1 AND fold='dev' AND {view}<>''),
     t AS (SELECT entity_id tid, country, {view} k FROM feat WHERE source IN (2,3) AND {view}<>''),
     blocks AS (SELECT country, k, count(DISTINCT s1) nq FROM q GROUP BY 1,2),
     tsz AS (SELECT country, k, count(*) nt FROM t GROUP BY 1,2)
SELECT count(*) FILTER (WHERE nq*nt > :cap) AS oversized_blocks, max(nq*nt) AS largest_pairs
FROM blocks JOIN tsz USING (country, k);
-- then equality-join q and t on (country, k) for blocks under the cap and left-join truth_pairs.
```

**Proposed promotion rule (a team choice, to agree with B):**
- *Retrieval channel:* adds >= 0.3 pp micro link recall over the union of existing channels, **or** lifts a slice by >= 2 pp; and its p95 candidates-per-query increase stays within the agreed budget.
- *Feature only:* helps discrimination but adds too much candidate volume (expected for `name_core` alone, see the collision table).
- *Reject:* no measurable gain or negative on any slice (dropping bracket text alone would have been rejected by this rule).

**Deliverable.** A decisions table (view, gain, cost, verdict) appended to `cleaning_decisions.md`; updated version if any rule changes (a new `feat_v2_1` directory).

---

### Phase 9. Handoff, resource report, review

Send B the package required by the doc:
1. Feature schema (section 3.4) and versions.
2. Input manifest and row-count reconciliation.
3. Fixtures across all scripts and France (`tests/fixtures/cleaning_fixtures_v2.tsv`).
4. Collision counts before/after each view, **especially distinct S1 IDs**.
5. Missingness and parse-confidence definitions.
6. Read commands, memory notes and paths (`read_parquet(..., hive_partitioning=true)`).
7. Known failure modes and ablation questions.

**Resource report** (`reports/cleaning/resource_report.md`): wall-clock, workers, peak RSS per worker, total disk, per-phase time; this feeds the SageMaker configuration.

**Review of B's work** before training starts: check the fold manifest for leakage (no target in a fold different from its owner; the same S1 never in two folds), the scorer on the six documented cases, and that no validation/holdout label influenced a lexicon (each label-derived mapping must cite the fold it was fitted on).

**Known failure modes to hand B** (all measured): near-duplicate S1 records (`Lille Club SAS`); initialisms (`Johns Group` vs `JG`, S1-827587640 -> S3-5118647); changed numbers (`1406`->`140`, `4298`->`4300`, `1324`->`132`); different localities for the same business (`Lysander` vs `Baldwinsville`); generic token replacement (`Northern Cardiology` vs `Northern Center`); `NA` names resolvable only by address.

---

## 5. Schedule against Member B (aligned to the team plan's five sessions)

| Session | A | B (from the team plan) | Sync point |
|---|---|---|---|
| 1 | Phase 0 and 1; start `cleaning_decisions.md` review | Review labels and scorer | Agree versions, freeze fold **first**, fixture IDs |
| 2 | Phase 2 and 3 | Freeze folds; R1/R2 baselines on **v1 keys** | Hand over hygiene + name fixtures |
| 3 | Phase 4 bake-off (needs the fold) and Phase 5 | Rare-token / n-gram retrieval | Compare recall/cost; inspect misses together |
| 4 | Phase 6 full build and Phase 7 QA | Hard negatives, pair EDA | Freeze `feat_v2_x` + retrieval version |
| 5 | Phase 8 ablation and Phase 9 handoff | Final candidate evaluation, leakage checks | Sign the ready-for-training checklist |

B can start on v1 keys immediately; nothing in A's plan blocks B until Phase 6.

**How B consumes the views** (mapping to the team plan's retrieval passes):

| Pass | Uses |
|---|---|
| R1 country + exact name | `name_key`, gated `name_core` |
| R2 country + exact address | `address_key`, gated `address_canon` |
| R3 rare name tokens | `name_core_set`, `name_ninformative` |
| R4 rare address token / number | `address_tokset`, `address_numbers_canon` |
| R5 / R6 character n-gram | `name_core` / `name_skeleton`, `address_canon` |
| R7 transliteration / accent | `name_translit`, `name_skeleton`, `name_latin_accent_key` |
| R8 weak-query fallback | name views when `address_missing`; **address views when `name_placeholder_like`** |

---

## 6. Risk register

| Risk | Evidence | Mitigation |
|---|---|---|
| Over-normalization creates false candidates | `name_core` raises S1 sharing 31% -> 41%, largest group 253 -> 572 | Phase 8 gating; never an identity key; keep full name and address in every table |
| Legal-lexicon scoping deletes real words | `private`, `sci`, `pc`, `sa`, `co` are ordinary words in some contexts | Country tiers; token-boundary matching; scoping fixtures |
| Skeleton collisions | Vowel removal | Auxiliary only; per-script collision report in the bake-off |
| France unvalidated | No French labels | Country-independent rules, conservative flags, France coverage reported separately, no French score claimed |
| Lexicon leakage | Label-derived native state mappings | Fit on dev fold only; cite fold in the lexicon header |
| Time/memory | 24.2M rows; 16 GB machine | Batched workers; measure before scaling; sample builds first |
| Version drift between A and B | Two people, one cache | New version = new directory; manifest hash recorded by every downstream artifact |
| Mojibake repair harms multilingual text | Global Latin-1 round trips corrupt scripts | Explicit narrow pattern only; ftfy limited to flagged rows and to an experiment |
| `St` ambiguity | Saint vs Street | Expand only at segment end (US); `st`/`ste` = saint (France) |
| No git repository | Directory is not a repo | Source-tree hash in the manifest; consider `git init` (D2) |

## 7. Decisions needed

| # | Decision | Recommendation |
|---|---|---|
| D1 | Add `pyarrow`, `anyascii`, `psutil`, `ftfy` (permissive licenses, verified) in a new `requirements-features.txt` | Yes |
| D2 | `git init` now so source revisions can be logged | Yes, before Phase 2 (ignore `data/`, `.venv/`, `student_resource/dataset/` as the existing `.gitignore` already does) |
| D3 | Compute v2 fields in Python (single implementation), keep DuckDB for verification and ablation | Yes |
| D4 | B freezes the fold manifest before A fits label-derived mappings | Yes, in session 1-2 |
| D5 | Apostrophe/elision policy for French (`L'EGLISE`: split vs join) | Emit both views; decide in Phase 8 by collisions |
| D6 | Who owns `generic_tokens_<country>.tsv` review | A curates; B challenges with hard-negative evidence |

## Appendix A. Commands

```powershell
# Baseline
.venv\Scripts\python.exe -m unittest discover -s tests -v
# Environment (Phase 0)
uv pip install --python .venv\Scripts\python.exe pyarrow anyascii psutil ftfy
# Phases 1, 6, 7
.venv\Scripts\python.exe scripts\build_manifest.py
.venv\Scripts\python.exe scripts\build_features.py --version feat_v2_0_sample --max-groups 1 --workers 6
.venv\Scripts\python.exe scripts\build_features.py --version feat_v2_0 --workers 6
.venv\Scripts\python.exe scripts\verify_features.py --version feat_v2_0
# Phase 8
.venv\Scripts\python.exe scripts\view_ablation.py --version feat_v2_0
# Read a partition from DuckDB
.venv\Scripts\python.exe -c "import duckdb; print(duckdb.sql(\"SELECT * FROM read_parquet('data/features/feat_v2_0/**/*.parquet', hive_partitioning=true) LIMIT 5\"))"
```

The scripts named above do not exist yet; they are the deliverables of the phases that introduce them.

## Appendix B. Fixture IDs (all observed in the data; see the register for text and rule)

| Topic | IDs |
|---|---|
| Legal form moved / bracketed / dropped | S1-682967345 -> S3-255756343; S1-964363270 -> S2-717577572; S1-664310844 -> S2-340920626; S1-471492511 -> S3-978815058 |
| Dotted acronyms | S1-707077753 -> S3-60481867; S1-12118664 -> S3-743763288; S1-21960160 -> S2-867034949 |
| Accent noise | S1-2343371 -> S2-403049977; S1-762337004 -> S3-952997408 |
| Domain form / prefix | S1-812342234 -> S2-503128682; S1-769774046 -> S2-164739466; S1-715948781 -> S3-286815238 |
| Placeholder names | S3-391601813 <-> S1-15071715; S3-640593334 <-> S1-707575573; S2-102598836; *(test France)* S2-109029910, S3-131417344 |
| Zero pad, abbreviation, `null` | S1-691809108 -> S2-990739088; S1-715948781 -> S3-286815238 |
| State forms | S1-746954052 -> S3-138403312; S1-812971315 -> S3-891304017; S1-737170761 -> S2-540633362 |
| Reordered components | S1-928129165 -> S2-366844796; S1-404757015 -> S3-568771724 |
| Number labels | S1-707077753 -> S3-60481867; S1-549145857 -> S2-217734940; S1-719621226 -> S3-871867799 |
| ZWNJ | S2-100080376 (Kannada), S2-100119914 (Telugu) |
| Mojibake | S2-102464820 (train), *(test)* S3-101145657, S3-102350063 |
| Bengali / Telugu cross-script | S1-809824196 -> S2-840805166; S1-477898461 -> S3-352574101; S1-737170761 -> S2-540633362 |
| France ambiguity *(test)* | S1-202327133, S1-628518958 (`Lille Club SAS`) |
| Initialism | S1-827587640 -> S3-5118647 (`Johns Group` vs `JG`) |
