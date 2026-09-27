# ML implementation phases: 0.95 macro-F0.5 target

Prepared 26 September 2026. This is the execution plan for building the model stack while Member B completes the frozen fold and candidate artifacts.

## Objective and non-negotiable constraints

- Primary optimization target: **0.95 macro-averaged F0.5 on the locked local holdout**.
- Minimum release candidate: **0.85 macro-F0.5**. A result below this remains experimental.
- Pairwise accuracy, ROC-AUC, and training loss are diagnostics only; they never select the winning system.
- Every experiment includes all S1 queries, including singletons and zero-candidate queries.
- False positives receive special attention because F0.5 penalizes a false match four times as heavily as a missed match in count form.
- No external business lookup, geocoding service, registry, or identity API is permitted.
- All learned models and dependencies used in the submission must satisfy the challenge's license and parameter-count rules.
- France remains an unlabeled, open-country generalization problem. No measured France score may be claimed.

## Target architecture

```text
feat_v2_0 records
      |
      +--> multi-channel sparse/semantic retrieval (Member B contract)
      |            target: >=99% link recall, >=0.97 oracle macro-F0.5
      |
      +--> pair feature builder
                   |
                   +--> calibrated GBDT scorer
                   |
                   +--> optional multilingual bi-encoder features
                   |
                   +--> optional cross-encoder top-k reranker
                                  |
                                  +--> query-level F0.5 decision policy
                                                 |
                                                 +--> submission export + validation
```

The GBDT is the mandatory workhorse. Neural models are promoted only after an ablation shows a locked-fold gain. Large models are not assumed to be better: retrieval recall, hard negatives, calibration, and abstention are expected to dominate early gains.

## Phase 0 - Contracts, metric, and reproducibility foundation

**Can start now:** yes. **Depends on Member B:** no.

**Implementation status:** complete and tested in `src/modeling/` (26 September 2026).

Build:

- Package layout for metrics, pair features, models, calibration, decision policy, inference, and export.
- Typed schemas for feature records, candidates, pair rows, scored pairs, query decisions, and experiment reports.
- Exact macro-F0.5 scorer, including singleton behavior and official edge cases.
- Deterministic configuration loading, seeds, structured logging, artifact manifests, and content hashes.
- Experiment record containing source revision, feature/candidate/fold versions, hyperparameters, runtime, memory, and slice metrics.
- Unit tests for invalid IDs, duplicates, missing S1 rows, empty predictions, and candidate-subset violations.

Exit gate:

- Metric edge cases reproduce the official expected values.
- Repeated runs with the same input and seed create identical decisions.
- No ID, source, split, fold, truth cardinality, or label-derived field can enter the learned feature matrix.

## Phase 1 - Pair-feature engine

**Can start now:** yes. **Depends on Member B:** no; use a small deterministic adapter fixture until the real candidate table arrives.

**Implementation status:** complete against the `candidate_v1` adapter contract; full-scale candidate data remains a Member B input.

Build a streaming/DuckDB/Arrow feature join over `feat_v2_0`. It must avoid loading tens of millions of Python strings into memory.

Feature families:

1. Name similarities across conservative, core, compact, token-set, accent, transliteration, and skeleton views.
2. Address token, character, segment, state, city-candidate, postal-candidate, and parse-confidence comparisons.
3. Numeric span overlap, conflict counts, and context agreement.
4. Script combinations, cross-script flags, missingness, placeholder flags, and text-quality indicators.
5. Retrieval channel, rank, score, channel agreement count, and ambiguity/block-size features.

Exit gate:

- Chunked output is deterministic Parquet with an explicit schema.
- Feature parity tests pass on handcrafted true/false examples.
- Peak memory is measured on 10k and 100k candidate-query samples.
- The builder accepts a versioned candidate contract without knowledge of the retrieval implementation.

## Phase 2 - Model and decision-layer baseline

**Can start now:** yes, using fixture/sample pairs. **Final results depend on Member B:** yes.

**Implementation status:** base complete and tested with both XGBoost and LightGBM, calibration, policy search, slice reporting, inference, and strict export. No real validation score is claimed before the frozen folds/candidates arrive.

Implement:

- XGBoost and LightGBM-compatible training adapters behind one interface.
- Early stopping and experiment logging.
- Hard-negative strata and sampling-weight support.
- Isotonic and Platt calibration adapters.
- Query-level policy search over empty, top-k, score threshold, score margin, and maximum-cardinality decisions.
- Per-country and per-slice reports.

The first production candidate will be a shallow, regularized GBDT. Hyperparameter search optimizes end-to-end validation macro-F0.5, not pair loss.

Exit gate:

- A synthetic/sample experiment runs from pair rows through exported predictions.
- Threshold search includes an empty prediction for every query.
- Calibration is fitted on data disjoint from model fitting.
- The policy can use conservative thresholds for weak-evidence slices without hard-coding known countries.

## Phase 3 - SageMaker execution foundation

**Can start now:** yes. **Depends on Member B:** no.

**Implementation status:** local foundation complete and tested (job entry points, containers, pipeline DAG, quality gates, metrics,
timeouts, versioned S3 contract, budget guard/ledger, deterministic cloud fixture, and local end-to-end smoke). The first AWS mutation is
blocked until the currently configured root credentials are replaced with a least-privilege temporary deployment identity and execution
role. See `docs/SAGEMAKER_RUNBOOK.md`.

Use SageMaker for repeatable full-scale jobs, not for an always-on endpoint.

Create:

- Versioned S3 layout for features, folds, candidates, pairs, experiments, models, predictions, and submissions.
- Processing-job entry points for pair construction, evaluation, and export.
- Script-mode XGBoost/LightGBM training job.
- Hugging Face/PyTorch training and batch-scoring entry points for optional neural stages.
- A SageMaker Pipeline DAG with parameterized sample/full modes and conditional quality gates.
- CloudWatch metric emission for candidate recall, oracle F0.5, model F0.5, singleton false-positive rate, runtime, and memory.
- Runtime caps, tags, encryption settings, and a budget ledger.

Initial resource policy:

- Develop locally and run 10k/100k sample jobs before scaling.
- Use memory-optimized CPU for pair construction and GBDT unless a measured GPU XGBoost trial is faster per completed experiment.
- Use a single G5-class GPU for embedding and reranker trials; scale only after a measured gain.
- Use Managed Spot plus checkpoints for interruptible neural jobs.
- Do not keep notebook kernels or endpoints running when a batch job is sufficient.

Budget envelope for the approximately USD 200 credit pool:

- USD 15: infrastructure and sample-pipeline validation.
- USD 35: GBDT full runs and bounded hyperparameter search.
- USD 60: multilingual embedding generation/fine-tuning experiments.
- USD 50: cross-encoder trials and final batch reranking.
- USD 40: final full inference, reruns, and contingency.

Exit gate:

- Sample pipeline is reproducible from S3 inputs to validated outputs.
- Every job has a timeout and versioned artifact prefix.
- No single tuning job can consume the contingency allocation unattended.

## Phase 4 - Member B integration gate

**Can start now:** interface/tests only. **Depends on Member B:** yes.

Required inputs:

- `fold_manifest_v1.parquet` with deterministic 80/10/10 group assignment.
- Tested official scorer and leakage report.
- Versioned candidate table with retrieval provenance.
- Candidate recall-versus-size report and oracle macro-F0.5.
- Hard-negative sampling specification.

Mandatory acceptance gates before claiming a model score:

- Candidate micro link recall >=99.0%; >=99.5% remains the stretch target.
- Candidate oracle macro-F0.5 >=0.97 for a credible path to 0.95 final F0.5.
- Metrics are computed after the final candidate cap.
- No severe failure is hidden in country, source, cross-script, missing-address, placeholder-name, or high-cardinality slices.
- No pair-row random split or ownership leakage exists.

If the oracle gate fails, work returns to retrieval. A better classifier cannot recover candidates it never sees.

## Phase 5 - Full GBDT system

**Depends on Member B:** yes.

Training data:

- All retrieved positives.
- Five to twenty hard negatives per positive, stratified by retrieval failure type.
- A small random-negative stratum.
- Logged sampling probabilities/weights.
- Retrieval misses are never relabeled as negatives.

Experiments:

1. XGBoost baseline.
2. LightGBM baseline.
3. Feature-group ablations.
4. Hard-negative curriculum iterations.
5. Calibration comparison.
6. Query decision-policy optimization.
7. Small, bounded hyperparameter search using end-to-end macro-F0.5.

Release ladder:

- `<0.80`: diagnose the pipeline; do not add model complexity blindly.
- `0.80-0.8499`: improve retrieval failures, hard negatives, and decision policy.
- `0.85-0.8999`: preserve as the minimum release candidate; continue controlled improvements.
- `0.90-0.9499`: strong candidate; neural additions require measured ablation gains.
- `>=0.95`: freeze and reproduce on the untouched holdout before final fit.

## Phase 6 - Multilingual semantic retrieval and representation

**Depends on a stable Phase 5 baseline:** yes.

Evaluate permissively licensed multilingual bi-encoders under the challenge's model constraints. Record the exact model revision and license before downloading it into the reproducible environment.

Uses:

- ANN retrieval channel for cross-script, alias, spelling, partial-address, and France-like cases.
- Name/address cosine features for the GBDT.
- Optional contrastive fine-tuning using development-fold positives and hard negatives.

Exit gate:

- Candidate recall/oracle improves at a controlled candidate-size cost, or locked validation macro-F0.5 improves after classification.
- The gain survives cross-country and difficult-slice evaluation.
- Otherwise, the neural retrieval channel is removed from the final system.

## Phase 7 - Cross-encoder precision reranker and ensemble

**Depends on Phase 6:** preferably. **Required for final system:** only if it wins validation.

- Rerank only the top 20-30 GBDT candidates per query.
- Train on difficult positives and hard negatives, not random easy pairs.
- Compare GBDT-only, cross-encoder-only, weighted blend, and stacked calibration.
- Retune the query-level abstention/cardinality policy after blending.

Exit gate:

- Statistically meaningful macro-F0.5 improvement on validation.
- No unacceptable increase in singleton false-positive rate.
- Inference fits the remaining SageMaker budget and submission timeline.

## Phase 8 - Robustness, France strategy, and locked holdout

- Train-on-US/validate-on-India and the reverse as domain-shift stress tests.
- Verify an open-country fallback with no `{US, India}`-only encoding.
- Audit France candidate counts, zero-candidate rate, scripts, accents, missingness, and score distributions without claiming accuracy.
- Compare calibration and abstention behavior across supported slices.
- Run the untouched holdout only for major frozen versions.

Exit gate:

- Minimum candidate: >=0.85 locked-holdout macro-F0.5.
- Target candidate: >=0.95 locked-holdout macro-F0.5.
- No critical slice or format regression.

## Phase 9 - Final fit, inference, and submission

- Freeze code, dependencies, feature schema, candidates, thresholds, and model licenses.
- Refit with the frozen procedure on development-train plus validation; keep the locked holdout out of tuning decisions.
- Generate test candidates, pair features, scores, calibrated probabilities, and final query decisions.
- Export `candidate_pairs.tsv` and `matching_results.tsv`, preserving the candidate-subset invariant.
- Run the official validator and independent row/count/hash checks.
- Produce the reproducible code package, requirements lock, model manifest, and methodology document.

## Immediate implementation order while Member B is pending

1. Phase 0: package contracts, scorer, manifests, and tests.
2. Phase 1: streaming pair-feature engine and feature parity tests.
3. Phase 2: GBDT/calibration/decision interfaces and sample end-to-end run.
4. Phase 3: SageMaker sample pipeline and cost controls.
5. Phase 4 interface tests: validate Member B's artifacts automatically when delivered.

This order produces a production-quality base without inventing labels, candidates, or validation results that belong to Member B's work.
