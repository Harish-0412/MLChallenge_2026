# Validation protocol `val_v1` (frozen 26 September 2026)

Owner: Member B. Code: `src/validation/` (splits, scorer, leakage), `scripts/build_fold_manifest.py`, `scripts/label_summary.py`. Tests: `tests/test_validation.py`.
Everything below is reproducible by another member: `python scripts/build_fold_manifest.py --check` rebuilds the folds from scratch and requires the same content digest.

## 1. What is split

| Item | Rule |
|---|---|
| Unit | one Source-1 (S1) identity: a query and **all** of its true S2/S3 targets always sit in the same fold |
| Data | **training** files only (2,206,821 S1 queries, 10,320,219 S2/S3 targets, 7,638,365 positive links). No test record enters any fold, and no fold is inferred from an ID number |
| Folds | `dev` 80% (fit and tune), `val` 10% (decisions, thresholds), `holdout` 10% (locked; run only for frozen versions) |
| Strata (queries) | country (India, US) x number of true targets in the buckets `0, 1, 2, 3-4, 5+` |
| Labeled targets | assigned to their owner's fold (7,638,365 links, 0 cross-fold) |
| Unmatched targets (2,681,854 S2/S3 records without an owner) | assigned by the same rule inside (country, source), so every fold keeps realistic distractors |
| Seed | `mlch2026-val-v1` (in `src/validation/splits.py`) |

## 2. The assignment rule (a pure function)

```
hash = sha256("<seed>|<role>|<entity_id>")            role = query | target
rank = position of the entity in its stratum sorted by (hash, entity_id), 1-based;   n = stratum size
fold = dev if rank <= floor(8n/10);  val if rank <= floor(9n/10);  holdout otherwise
```

Each stratum therefore has **exactly** the 80/10/10 floor split, not an approximate random one. The rule is implemented twice (DuckDB SQL in `splits.build_manifest`, hashlib in `splits.assign_folds_python`); the leakage check L10 requires them to agree on all 2.2M queries and all unmatched targets.

Result (`data/splits/fold_manifest_v1.parquet`, 12,527,040 rows; content digest in `reports/eda/fold_manifest_v1.json`):

| fold | queries India | queries US | singleton fraction | links per query | targets (owned + unmatched) |
|---|---:|---:|---:|---:|---:|
| dev | 706,548 | 1,058,904 | 0.05588 / 0.05583 | 3.465 / 3.459 | 8,256,413 |
| val | 88,319 | 132,363 | 0.05588 / 0.05583 | 3.463 / 3.456 | 1,031,503 |
| holdout | 88,321 | 132,366 | 0.05589 / 0.05583 | 3.464 / 3.461 | 1,032,303 |

The manifest columns: `entity_id, role, source, country, fold, stratum, match_count (queries), owner_id (labeled targets), assignment (stratified_hash | owner | unmatched_hash), fullcorpus_sample`.
The file is 106 MB and lives in `data/splits/` (not in git); share it through S3 and verify the digest.

## 3. Two retrieval protocols (never mix their numbers)

* **Protocol A, isolated fold.** Queries of a fold retrieve only from that fold's targets (owned + unmatched). A record can never be a training negative and a validation positive. The corpus is about 1.0M targets for `val`/`holdout`, about 8.3M for `dev`, so recall here is *easier* than at test time.
* **Protocol B, full-corpus stress test.** A deterministic sample of held-out queries (`fullcorpus_sample = true`: up to 20,000 per fold x country from `val` and `holdout`) retrieves from the **complete training target corpus** (10.3M), which is the size the real test faces (test S2+S3 has 9.97M targets). Report separately as "full-corpus". Its held-out labels are never used to train protocol A.

## 4. Stress split `stress_name_v1` (`data/splits/fold_manifest_stress_v1.parquet`)

S1 entities that share `(country, name_key)` are one group and are assigned together, so a common business name can never be split between `dev` and `holdout`. India: 559,665 groups (largest 99 records, 392,116 queries sit in a shared-name group); US: 961,759 groups (largest 253, 474,025 queries in shared-name groups). Groups are ranked within country by hash; fold sizes are therefore about 80/10/10 of *groups* (dev 10,019,256 / val 1,254,898 / holdout 1,252,886 rows). The exact-payload split (same name+address key) has **no** effect on training data: there is no duplicate S1 tuple in the training labels (0 groups), so it equals the entity split. Two French test records that do share a tuple (`S1-202327133`, `S1-628518958`) are recorded as an ambiguity, not merged.

## 5. What is fitted on what (freeze)

* Dictionaries, IDF/token frequencies, alias tables, thresholds, feature selections, calibration and decision policy are fitted on `dev` only. `val` is used to choose among fitted candidates; `holdout` is touched only to score a frozen version.
* Reading `val`/`holdout`/test records to *index and transform* them is allowed; learning a supervised mapping from their labels is not.
* Corpus-level unsupervised statistics (for example IDF over all targets of a protocol) must be stated per experiment and reproduced identically at final inference.
* Earlier exposure: the descriptive audit (`reports/eda/full_audit.json`, EDA findings, A's 0.5% positive-pair samples) looked at aggregate statistics of **all** training labels before this split existed. Those numbers are exploratory. From this freeze on, no one inspects errors on `holdout`.
* France has no labels: no fold, no score. Any French statement is candidate counts, script coverage and examples only.

## 6. The metric

Macro-averaged per-entity F0.5 over **every** required S1 in the evaluated set, singletons and zero-candidate queries included:
`F0.5_i = 1.25 TP / (1.25 TP + FP + 0.25 FN)`; empty truth and empty prediction = 1, empty truth and any prediction = 0, non-empty truth and empty prediction = 0.

Implementations (`src/validation/scorer.py`): `macro_f05_sets` (reference; rejects duplicate IDs, missing or extra queries, non S2/S3 targets) and `macro_f05_tables` (DuckDB, for millions of queries; rejects duplicate prediction rows and unknown queries). Both are checked against the six documented cases, against each other and against the independently written `src/modeling/metrics.py` on random data. The all-empty baseline equals the fold's singleton fraction on every fold (0.0558475 dev, 0.0558496 val, 0.0558529 holdout, 0.0558482 overall).

## 7. Leakage checks (all pass, `reports/eda/fold_leakage_report.md`)

L1 unique entities; L2/L3 exactly the training entities; L4 fold values; **L5 no true link crosses folds (0 of 7,638,365)**; L6 owner ids equal the ground truth; L7 no labeled target treated as unmatched; L8/L9 exact 80/10/10 per stratum; L10 independent hashlib recomputation; L11 the fold does not track the ID number; L12/L13 the all-empty baselines; L14 the full-corpus sample holds only held-out queries; L15-L17 the stress protocol. Each check is exercised by a sabotage test that proves it can fail.

## 8. Rules for everyone using the folds

1. Never split expanded pair rows at random and never sample S2/S3 independently of query truths.
2. A candidate target owned by a held-out query must not appear as a training negative (guaranteed by protocol A; check it when building protocol B training sets).
3. Retrieval misses are never relabeled as negatives; injected positives (if ever used) carry a training-only flag excluded from features.
4. Report all metrics after the final candidate cap, over all queries of the fold, with the per-slice table from `label_summary.md`.
5. To change any part of this protocol, create `val_v2` (new seed/version); never edit the frozen files.
