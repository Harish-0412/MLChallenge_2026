# Member B: label EDA, validation and candidate generation

Your responsibility is to show whether the cleaned representations can recover the right records at realistic scale. You own labels, validation splits, the metric, candidate retrieval and the preparation of training pairs. Member A supplies versioned record features.

Read the [shared plan](TEAM_PRETRAINING_PLAN.md) and [measured findings](../reports/eda/EDA_FINDINGS.md). You work on all countries and both target sources; France has no labels, so you can inspect its data/retrieval volume but cannot report French recall or F0.5.

## What is ready now

- `reports/eda/full_audit.json`: label integrity, cardinality, overlap and exact-key oracle ceiling.
- `reports/eda/match_count_distribution.csv`: full country-level label distribution.
- `reports/eda/positive_pair_profile.csv`: full positive-link equality/missingness/numeric-conflict statistics.
- `reports/eda/positive_pair_sample_s2.csv` and `...s3.csv`: a deterministic sample for fuzzy similarity exploration.
- `scripts/normalization.py`: tested per-entity F0.5 helper.
- `data/interim/audit.duckdb`: record tables, `truth_rows`, `truth_pairs` and coverage diagnostics.
- `data/interim/*_source*.parquet`: raw text plus comparison keys from A's initial contract.

No candidate retrieval benchmark, hard-negative dataset, frozen fold assignment or trained model is delivered yet. Your tasks below produce those pretraining artifacts.

## Your first session

1. Run existing tests and inspect label integrity and match-count distributions.
2. Read the exact-name/address recovery statistics. An exact-match baseline is useful but insufficient; quantify the missing slices before improving it.
3. Confirm the normalization schema with A, and choose a stable split protocol.
4. Create `reports/eda/validation_protocol.md` stating split units, target/distractor assignment, fit scope, seed and metric implementation.
5. Implement a dataset-level scorer and independent tests before evaluating a retrieval or later model change.

## B1. Label integrity and taxonomy

Keep the 2,206,821 reference queries separately from the 7,638,365 expanded positive pairs. An inner join on positive pairs would remove 123,247 singletons and bias every later result.

Verify every target ID exists in the correct training source, every S1 has exactly one label row, and all pair labels are unique. The current full audit passes these checks, shows country consistency and no target with more than one owner.

Create these slices: US/India, S2/S3, singleton, match count, missing target address, script combination, low name similarity, number disagreement and common names. Membership can overlap; state denominators clearly.

Inspect near-identical reference entities but do not merge or relabel official IDs. The current conservative key finds no exact duplicate S1 name+address+country groups. This does not exclude near duplicates or semantic ambiguity.

**Deliverable:** label-summary table and an error taxonomy usable in every later experiment.

## B2. Validation split and scorer

Create one fold assignment per S1 identity group. Start with country × match-count buckets `0,1,2,3-4,5+` and an 80/10/10 split. Put all true targets of an S1 into its fold. Assign unmatched targets deterministically to folds to preserve realistic distractors.

Never split pair rows at random. A candidate target must not be a training negative while its owner/query is held out. Check this explicitly with ID intersections and the ground-truth ownership table.

Save a separate stress split grouping identical normalized S1 payloads or carefully defined related identities. Use grouped stratification where needed; inspect group sizes and country/cardinality balance. A fixed split manifest matters more than repeatedly calling a random splitting function.

For the isolated-fold benchmark, retrieve from fold-specific targets. For a second, harder retrieval diagnostic, use sampled held-out queries against the complete training target corpus. Label the protocols clearly because a smaller retrieval corpus is easier. Do not use the second protocol's held-out labels to train the first protocol.

Freeze preprocessing fit scope: dictionaries, IDF, token frequency cutoffs and decision parameters are fitted on development-training data, unless a separately documented unsupervised indexing protocol is deliberately used. Do not copy official test records into training labels or infer identity from ID number patterns.

Metric cases to test:

| Truth | Prediction | Expected F0.5 |
|---|---|---:|
| empty | empty | 1 |
| empty | any match | 0 |
| nonempty | empty | 0 |
| `{a,b}` | `{a,b}` | 1 |
| `{a,b}` | `{a,b,c}` | 5/7 |
| `{a,b}` | `{a}` | 5/6 |

The all-empty baseline on the full labeled dataset is exactly the singleton fraction, about 0.0558482. Your local fold's all-empty score should equal that fold's singleton fraction. Average over every required S1, including zero-candidate queries. Predictions must be sets; separately reject duplicate ID lists rather than letting duplicates affect metric counts.

**Deliverable:** `fold_manifest.parquet`, split protocol, scorer and leakage tests. **Acceptance:** another member can recompute the same membership and scores.

## B3. First retrieval benchmark

Use 10,000 deterministic development-training queries covering country and match-count strata. Keep the full permitted target corpus for the chosen benchmark protocol. Do not sample S2/S3 independently in a way that drops query truths.

Build two equality indexes/joins separately:

1. `(country, name_key)` with nonempty names.
2. `(country, address_key)` with nonempty addresses.

Union and deduplicate pair IDs while retaining both retrieval reasons. Count block sizes before expansion; an overlarge block needs secondary keys or ranked selection. Do not let an empty address match every other empty address.

Measure true-link recall, complete-entity coverage, candidate-count quantiles, total pairs and runtime. If you cap candidates, report metrics before and after the cap. The all-data exact-key oracle in the audit assumes no cap; your bounded implementation may perform worse.

**Deliverable:** reproducible baseline candidates and a benchmark row, with no learned classifier involved.

## B4. Expand retrieval based on failures

Add one retrieval channel at a time:

| Failure | Candidate improvement |
|---|---|
| Name typo / word-order change | Character n-grams and rare name tokens |
| Missing address | Strong name retrieval and ambiguity controls |
| Different-script name | A's tested transliterated view plus address retrieval |
| Strongly different alias name | Address retrieval and rare address tokens |
| Partial address / missing number | Address n-grams without an absolute number requirement |
| French accents / abbreviations | Accent auxiliary view and generic character retrieval |
| Common name | Secondary rare address/context key or bounded ranked retrieval |

Keep country as the first partition, consistent with all observed positive labels. Do not partition by a guessed city/state as the only path, because those fields can be absent, reordered or misspelled.

Choose a scalable sparse retrieval implementation with a local index. TF-IDF itself is a representation, not automatically an efficient nearest-neighbor system. Avoid `cosine_similarity(all_S1, all_targets)` and Python fuzzy loops over millions of rows. Use inverted postings or a top-k sparse engine and query in batches. Inspect RAM/disk growth before scaling from 10,000 to 50,000 queries.

Compare k values such as 10/20/50/100 per channel. Keep candidate provenance and scores separate. If a global budget trims the union, ensure address-only and cross-script candidates are not discarded simply because their name score is lower.

**Deliverable:** a recall-versus-size curve and per-slice missed-link table for each added rule. **Acceptance:** improvements are evaluated after the exact final filtering path that future inference will use.

## B5. Candidate quality gates

Record micro true-link recall, macro recall over non-singletons, all-true-links coverage, zero-candidate rate, oracle F0.5 ceiling and candidate-size quantiles. Show separate results for India/US, S2/S3, cross-script, missing-address and high-cardinality entities.

Aim initially for at least 99% micro link recall, with 99.5% as an aspirational refinement target. These are choices to guide development, not a pass guarantee. A low-performing slice still needs investigation even if the aggregate is high.

To compute the oracle ceiling, select only true links present in candidates and reject all incorrect ones, then use the official macro scorer. This establishes the classifier's best possible score with that candidate set. It does not measure actual classification.

For France, report candidate counts, zero-candidate fraction, text/script coverage and example quality only. Cross-country holdout experiments on US and India are stress tests, not estimates of measured French accuracy.

## B6. Hard-negative EDA and feature handoff

After retrieval is stable, label the generated development-training pairs using exact ground-truth membership. Analyze all positives plus stratified hard negatives from retrieval. Keep some random negatives for comparison, and log sampling weights/counts.

Do not relabel retrieval misses as negatives. Do not inject their true targets into validation candidates. If the later classifier needs augmented positives, keep an `injected_positive` training-only flag and exclude that flag from model features.

Feature groups to evaluate with A:

- Character and token similarity for raw/conservative/auxiliary name views.
- Rare-token overlap and legal-form agreement.
- Address character/token similarity and parsing-confidence flags.
- Numeric agreement/conflict, with missingness distinct from mismatch.
- Script combination and placeholder-like name indicators.
- Retrieval scores/ranks/provenance and candidate ambiguity counts.

Exclude IDs, truth match counts, fold labels, target ownership, injected-positive flags and any field derived from labels at inference time. Keep them only as metadata for audits.

Create a bounded review sample for each failure type. A single high fuzzy similarity score is not proof of identity. Document where the model will later need joint name-and-address evidence or abstention.

**Deliverable:** pair-feature schema, hard-negative sampling specification, per-slice plots/tables and a list of unresolved errors. No model training is required to complete this package.

## Handoff and team sign-off

Give A the split manifest, scoring tests, candidate schemas, exact per-slice recall/cost metrics, missed-pair examples and the proposed feature list. A reviews feature provenance and confirms their representations can be reproduced.

Together complete the [ready-for-training checklist](TEAM_PRETRAINING_PLAN.md#12-ready-for-training-checklist). The final candidate table must later be exportable to the challenge's one-row-per-S1 `candidate_pairs.tsv`, including empty rows; every final predicted match must be a member of that query's scored candidate set.
