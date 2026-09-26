# Model training analysis: from cleaned records to a maximum-F0.5 submission

Prepared 25 September 2026. Companion to [TEAM_PRETRAINING_PLAN.md](TEAM_PRETRAINING_PLAN.md) (phases 1-2) and [MEMBER_A_IMPLEMENTATION_PLAN.md](MEMBER_A_IMPLEMENTATION_PLAN.md) (phases 0-9). This document covers the *third* work package: what model we train, how, where, and why that maximizes the leaderboard metric.

Sources used: `student_resource/README.md` (problem statement, metric, constraints), `student_resource/utils/validate_submission.py` (output contract), `student_resource/Documentation_template.md` (required methodology write-up), `reports/eda/EDA_FINDINGS.md` (measured baselines), `docs/TEAM_PRETRAINING_PLAN.md` §13 (fair-play and license rules).

---

## 1. What "maximum accuracy" actually means here

The scoreboard is **macro-averaged per-entity F0.5** over every test Source 1 entity:

```
F0.5_i = 1.25 * TP / (1.25 * TP + FP + 0.25 * FN)        (count form)
```

Five properties of this metric drive every design decision below:

1. **A false merge costs 4x a missed match** in the denominator (FP coefficient 1.0 vs FN coefficient 0.25). A model tuned for recall (F1-style) will lose to a model tuned for precision. Threshold selection is as important as model quality.
2. **Macro average over all queries**: singletons (~5.58% of training S1) score 1.0 for a correct empty prediction. A "predict nothing" baseline already scores ≈0.0558. Conversely, one overconfident merge on a true singleton zeroes that entity.
3. **Per-query curves matter, not global accuracy**: an entity with 11 true matches has a very different F0.5 profile from one with 1. Training and thresholding should condition on predicted cardinality, not a single global score cutoff.
4. **The candidate set is a hard ceiling**: no model can score above the recall of blocking. The measured exact-key oracle is 0.5188 (28.80% link recall) — so retrieval quality is the single biggest score lever, before any classifier is trained.
5. **Public vs private leaderboard split**: rankings are final on the private half. Overfitting the public subset (by iteratively reading the public score) is a real risk; the frozen local validation fold is the decision surface, the public LB is a sanity check.

So the objective decomposes into: **maximize candidate recall → maximize per-pair discrimination → optimize per-query selection under a precision-heavy metric → protect singletons and low-evidence queries**.

---

## 2. Architecture: two stages, one contract

```
Stage 1 (retrieval / blocking)          Stage 2 (matching model)
S1 x S2/S3 universe: 1.7e14 pairs  -->  candidates: ~50-100 per query  -->  scored, calibrated, thresholded
R1..R8 channels (B's passes)            pair features -> GBDT (+ optional re-ranker)
target: >=99.5% micro link recall       target: maximize macro F0.5 on frozen validation
```

The submission package requires both artifacts: `candidate_pairs.tsv` (stage 1 output, exactly what the model scored) and `matching_results.tsv` (stage 2 output, subset of the former). The validator enforces the subset invariant — keep retrieval provenance so it holds mechanically.

### 2.1 Stage 1 — candidate generation (already planned, Member B)

The eight passes R1-R8 (exact name, exact address, rare tokens, rare address/numbers, name n-grams, address n-grams, transliteration/accent, weak-query fallback) with per-channel k sweeps and a union + dedup step. Measured evidence says which channels matter: exact keys alone reach only 28.80% of links; cross-script pairs are 23.4%/12.5% of India true links; `NA`-named queries are true links needing an address route.

**Training-time role of stage 1:** it also *manufactures the classifier's training set* — positives (ground-truth pairs present in candidates) and hard negatives (retrieved non-matches). This is why B's benchmark design (fold-specific targets, provenance, sampling probabilities) is a prerequisite for model training, not just evaluation.

### 2.2 Stage 2 — the matching model

See section 4 for the model ladder. Inputs are pair-level features built from A's `feat_v2_0` views; output is a calibrated match probability; a per-query decision layer converts probabilities into the final ID list.

---

## 3. Pair features (what the model actually sees)

Grouped by A's feature version `feat_v2_0` (55 columns) plus retrieval provenance:

| Group | Features | Why |
|---|---|---|
| Name similarity | RapidFuzz ratio/token_set on `name_hyg`, `name_core`, `name_core_set`, Jaccard on token sets, char 3-5 gram cosine, compact-view equality | Core signal; graded similarity beats equality (Jaccard ≥ 0.8 fits 52-63% of India true pairs) |
| Name structure | `legal_form` agreement (none/one/both differ), `name_core` equality, `name_is_domain_like`, `name_ninformative`, duplicate-token counts | Legal-form strip is the largest measured name lever (+18 to +33 pp exact agreement) |
| Script/translit | `name_scripts` bitmask combination, cross-script indicator, similarity on `name_translit`/`name_skeleton`, `name_latin_accent_key` ratio | Cross-script slice needs its own evidence; skeleton median 85-86 on core |
| Address similarity | ratio/Jaccard on `address_canon`, `address_tokset`, `address_segset`, segment overlap, state equality + confidence (`exact`/`alias`/`mapped_native`/`none`) | State canonicalization + abbreviation expansion are the biggest address levers |
| Numbers | span-set Jaccard on `address_numbers_canon`, shared span count, conflicting span count, `address_number_ctx` agreement | Numbered evidence is graded, never a veto (true pairs can disagree) |
| Missingness/quality | `address_missing` both sides, `name_placeholder_like`, `address_parse_conf` pair, mojibake/control flags | Missing ≠ mismatch; placeholders need an address-only route |
| Retrieval provenance | channels that fired, per-channel rank, retrieval scores, candidate ambiguity (how many targets share the query's key) | Strong priors: a pair found by 3 channels is likelier than one found by fallback |
| Blocked identity | `country` equality (constant by construction), entity-count priors of shared tokens | Country is an observed blocking rule; token-frequency priors are corpus statistics |

**Leakage rules for the feature builder** (already fixed in the team plan): no `entity_id`, no `id_num`, no `source`/`split`/`fold` as raw features; label-derived mappings (native state names, transliteration choice, token frequencies) fitted on the development-training fold only; corpus statistics documented and identical across folds and final inference.

---

## 4. Model ladder: what to train, in what order

Each rung is a complete, submittable system. Move up only when validation shows a measured F0.5 gain that survives the precision-side cost.

### Rung 1 — Calibrated GBDT pair classifier (the workhorse)

- **Model:** LightGBM (MIT) or XGBoost (Apache-2.0) binary classifier on the pair-feature table. ~50-200 trees, shallow depth (3-6), heavy early stopping — the goal is a *calibrated probability*, not a Kaggle-max complex fit.
- **Training data:** every positive pair whose target was retrieved by stage 1 (≈99%+ of the 7.6M training links) + hard negatives sampled per query (5-20 per positive; strata: name-similar, address-similar, number-conflict, transliteration collision, common-name) + a small random-negative stratum. Log sampling weights for later calibration.
- **Calibration:** isotonic or Platt on the validation fold, fitted on group-structured data (per query, not per pair). GBDT scores are not probabilities out of the box.
- **Decision layer:** per query, sort candidates by calibrated probability and choose the subset maximizing expected F0.5 (or a probability threshold tuned per cardinality bucket on validation). Include an *abstain band*: when the top score sits in a low-evidence region (e.g., weak fallback channel, placeholder name, missing address both sides), predicting empty is often the F0.5-optimal move.
- **Why first:** it trains in minutes on CPU, consumes the engineered features that A is already building, is fully reproducible on this 16 GB machine, and historically wins or ties deep models on ER pair classification when blocking recall is equal. It also gives the fastest measured feedback into A's ablation loop (Phase 8).
- **Expected ceiling with strong blocking:** the exact-key oracle is 0.5188; GBDT + fuzzy channels in published ER systems typically recover a large share of the gap between the exact oracle and 1.0; the exact number here is an empirical question the validation fold answers.

### Rung 2 — Multilingual bi-encoder embeddings (recall insurance, optional)

- **Model candidates** (all satisfy the ≤8B / MIT-Apache constraint): `paraphrase-multilingual-MiniLM-L12-v2` (~118M, Apache-2.0), `intfloat/multilingual-e5-base` (~278M, MIT), `BAAI/bge-m3` (~560M, MIT).
- **Use:** encode `name_core` (+ address, either concatenated or as a second vector) for all 17M test/train records; add cosine similarity as *features* to the GBDT and/or as an R5/R7 alternative retrieval channel. Fine-tune with a contrastive objective on dev-fold pairs if a measurable gain appears.
- **Why it helps:** catches semantic aliases ("Northern Cardiology" vs "Northern Center") that surface rules miss; multilingual checkpoints handle the nine Indic scripts natively without transliteration.
- **Cost:** 24M records × 384-768 dims ≈ 18-35 GB — needs DuckDB/numpy-backed ANN (or a disk-based index), not brute force. This is the first rung that *needs* a GPU (hours, not minutes) and larger RAM.

### Rung 3 — Small cross-encoder re-ranker (precision finishing, optional)

- **Model:** a multilingual MiniLM-class cross-encoder (e.g., `mMiniLMv2-L6-H384-v2`-based, ~118M, Apache-2.0) fine-tuned on the same pair labels to output P(match) given `[CLS] name_core A [SEP] address A [SEP] name_core B [SEP] address B`.
- **Scope discipline:** re-rank **only the top-k (e.g., 30) GBDT-ranked candidates per query** — 1.7M queries × 30 ≈ 51M forward passes ≈ 4-7 h on one modern GPU, or ~2 h on four. Re-ranking the full 100-candidate set roughly triples that.
- **Why:** cross-encoders see both sides jointly and reliably beat feature-similarity stacks by a few points of precision at fixed recall — exactly what F0.5 rewards.
- **Only after rung 2 exists** (it shares the tokenizer/embedding infrastructure) and only if validation shows the GBDT's calibrated probabilities are leaving measurable precision on the table.

### What we deliberately do NOT train

- An end-to-end graph/listwise model over whole entity clusters (complex, hard to calibrate for F0.5, poor cost/benefit at this deadline).
- A >8B-parameter or non-permissive-license model (hard rule from the problem statement; audited in the final package).
- Any model that sees `entity_id`, fold, or label-derived counts as features.

---

## 5. Training procedure, step by step

1. **Freeze inputs.** `feat_v2_0` Parquet + `fold_manifest.parquet` (B2) + candidate table version `cand_vX` (B3/B4). Every experiment logs experiment_id, input hashes, source revision, feature/candidate/split versions, seed, runtime, per-slice metrics.
2. **Build the pair table.** Join candidates to features (compact `id_num` keys), expand labels from `train_ground_truth.tsv`, attach `is_positive` by exact membership. One row per pair, Parquet, no pandas object columns.
3. **Split discipline.** Train on dev-train fold pairs only. Validate on the validation fold *through the full inference path* (its own candidates, its own calibration, final caps). Never touch the locked holdout until the last pre-submission check. Missed-retrieval positives are retrieval failures, not negatives.
4. **Fit.** GBDT with early stopping on a stratified validation slice of dev-train; monitor AUC plus precision@high-recall operating points (F0.5 lives at high precision).
5. **Calibrate + threshold.** Isotonic on validation; then grid-search the per-cardinality decision policy (threshold, top-k cap, abstain band) to maximize **macro F0.5 over all validation queries, singletons included**. This step routinely moves macro F0.5 more than model choice does.
6. **Slice audit.** Report F0.5 and calibration error per country, source, cross-script, missing-address, placeholder-name, and match-count slice. A high aggregate with a broken cross-script slice is a failed experiment per the team plan.
7. **Ablate.** Drop each feature group; keep groups with measured validation gain. Feed the same evidence back to A's Phase 8 view promotions.
8. **Final fit for test inference.** After the last decision, refit on dev-train + validation (never holdout) with the frozen hyperparameters, re-calibrate, and run the full test inference: candidates → features → probabilities → decision layer → `matching_results.tsv`; emit `candidate_pairs.tsv` from the same scored set; run `validate_submission.py --check-ids`.
9. **Leaderboard hygiene.** Treat the public score as one noisy datapoint; do not tune on it. Ship the best *validation* system, not the best public-claiming variant.

**Class imbalance note:** positives are ~7.6M but the negative universe is ~10^14. After hard-negative sampling the training ratio is typically 1:5-1:20 — handle with scale_pos_weight / balanced sampling, and verify calibration afterward, because aggressive reweighting distorts probabilities.

---

## 6. Inference at test scale (why the design must stay cheap)

- Test universe: 1,732,544 S1 queries × 9.97M S2/S3 targets. At 50 final candidates/query ≈ 86.6M scored pairs; at 100 ≈ 173.3M.
- GBDT scoring of 173M rows × ~40 float features: minutes-to-an-hour on a 16-vCPU box, fully feasible locally.
- The expensive step is only the optional cross-encoder re-rank (section 4, rung 3). Everything else fits this machine; the resource report A produces in Phase 9 feeds the exact instance sizing.

---

## 7. SageMaker or not?

### What training here actually requires

| Workload | Compute | Duration | Notes |
|---|---|---|---|
| GBDT on ~30-50M pairs | 16-64 vCPU, 64-256 GB RAM | minutes to ~1 h | 16 GB local RAM is tight but workable with batched feature building; a 64-256 GB instance removes all friction |
| Embedding encode of 24M records (rung 2) | 1 GPU (g5.xlarge class) | ~1-3 h | plus ANN index build |
| Bi-encoder fine-tune (optional) | 1 GPU | ~1-4 h | small model |
| Cross-encoder re-rank inference (optional) | 1-4 GPUs | ~2-7 h | the only genuinely GPU-heavy step |
| Full pipeline orchestration + storage | S3 + a job runner | — | 2.5 GB TSVs, ~10+ GB Parquet, ~1-3 GB candidate tables |

### Honest comparison

| Option | Strengths | Weaknesses | Verdict |
|---|---|---|---|
| **This machine (16 GB, 12 cores)** | Free, zero latency, data in place; GBDT rung is fully feasible | Feature building and embedding index are memory-tight; no GPU | Primary dev environment — already proven by the full audit |
| **SageMaker Training/Processing** | Managed spot (60-90% off), checkpoints, experiment tracking, reproducible job images, Batch Transform for the 173M-pair sweep; teammates don't need local GPUs | Cost above raw EC2; setup overhead (images, IAM, S3 choreography); iteration loop slower than local | **Yes for full-data runs — if the team has AWS credits/budget**. It is the right tool for rungs 2-3 and for the final reproducible build |
| **Plain EC2 spot / Lambda Labs / Vast.ai** | 30-60% cheaper than SageMaker for the same GPU-hours; full control | You own the environment, storage and teardown; easy to waste money on idle instances | Fine if someone on the team enjoys ops; SageMaker's spot+checkpoint management is worth ~the price gap here |
| **Kaggle (30 GPU-h/week free) / Colab Pro** | Free or ~$10/month; P100/T4/V100-class GPUs | 30 h/week quota, 13-20 GB session RAM, session expiry makes 24M-record jobs clumsy, data upload friction | Genuinely viable free path for rungs 2-3 chunks; awkward as the main orchestrator |
| **Local GPU (if any team member has one)** | Fastest iteration, zero cost | — | Use it first if it exists |

### Recommendation (decision D7 for the team)

1. **Rung 1 (GBDT + decision layer) entirely local.** It is the highest score-per-hour investment and needs no cloud.
2. **Rungs 2-3 (embeddings/cross-encoder) on free GPU first** (Kaggle/Colab or a member's GPU). They are optional refinements, not dependencies of a strong submission.
3. **Move to SageMaker when a run is "real"**: full-data feature build, final model fit, and test inference. Use: SKLearn/Processing jobs for feature building (or keep DuckDB/Parquet steps local and upload derived Parquet), the built-in XGBoost or a script-mode job for GBDT, a HuggingFace estimator for any transformer step, Batch Transform for re-rank sweeps, SageMaker Experiments as the experiment log, managed spot + checkpointing, `ml.m5.4xlarge`/`r5.2xlarge` for CPU jobs and `ml.g5.xlarge`/`2xlarge` for GPU.
4. **If no AWS budget exists at all**, the complete system remains buildable: local GBDT + free-GPU embeddings, skipping the cross-encoder or running it on Kaggle in chunks. Nothing in the metric forces cloud spend.
5. **Reproducibility contract:** the final zip must regenerate outputs from code + data alone (`requirements.txt`, exact commands). Whichever compute runs it, the *scripts* are the deliverable — SageMaker is an accelerator, not an architecture.

The repo already anticipated this: Phase 9's resource report (runtime, peak RSS, disk) is exactly the input SageMaker instance sizing needs.

---

## 8. Is the current cleaning + EDA approach the right one?

**Yes — it is unusually well aligned with this specific competition.** Evidence:

1. **It is metric-driven, not tidy-data-driven.** Every cleaning rule is gated on "does it recover true links at acceptable collision cost" (Phase 8's promotion rule) — the correct question for a precision-heavy macro-F0.5 task. Generic cleaning (drop duplicates, strip accents globally, impute missing) would *destroy* signal: duplicate-looking S2/S3 payloads are separate required matches, `NA` names are true links, combining marks are script content.
2. **It preserves the two things a matcher needs: evidence and uncertainty.** Raw fields are kept byte-identical while multiple named views (accent-folded, legal-form-stripped, transliterated, token-set, number-span) are added. Missingness is a flag, not an imputation. That is exactly the feature interface section 3 consumes.
3. **The EDA found the real levers, quantified.** Exact keys = 28.80% recall → blocking must be multi-channel; cross-script = 23.4%/12.5% of India links → transliteration is mandatory, not optional; legal forms = biggest name lever; state canonicalization + abbreviations = biggest address lever; mojibake ≈ 0 pp → correctly demoted to hygiene. These measurements de-risk the entire model phase.
4. **Sequencing respects leakage.** Freezing the fold before fitting label-derived mappings is the discipline that makes section 5's training valid at all.

**Three watch-outs** (failure modes to actively avoid):

- **Do not let cleaning perfection delay the first retrieval benchmark.** B's R1/R2 baseline on the *existing* v1 keys is already unblocked; the GBDT rung can be prototyped on v1 features this week. Cleaning v2 raises the ceiling; it should not gate the loop.
- **Every aggressive view must report its precision-side cost**, not only recall gains. `name_core` sharing jumps 31%→41% on S1; used carelessly it floods the candidate table and the F0.5 punishes exactly that.
- **France and the unseen-country contract.** No model or lexicon may hard-code {US, India}; country-scoped lexicons with a generic fallback already handle this — keep the same rule in model features (country-conditioned priors must have an open-vocabulary default).

---

## 9. Timeline sketch (sessions 4-6 of the team plan)

| Session | Deliverable |
|---|---|
| 4 | Candidate table v1 (R1/R2 + rare tokens) on dev fold; pair feature table v1 on v1 keys; GBDT v1 + calibration + threshold; first measured validation macro F0.5 |
| 5 | feat_v2_0 features in; ablation-driven view promotion; R3-R8 channels complete; GBDT v2; slice audit; decision: is rung 2 worth it? |
| 6 | Optional embeddings/re-ranker; final refit; test inference; `matching_results.tsv` + `candidate_pairs.tsv`; validator PASS; methodology document filled; submission zip |

## 10. Risks

| Risk | Mitigation |
|---|---|
| Calibration drift between folds | Refit calibration on the fold being scored; monitor calibration error per slice |
| Hard-negative sampling bias | Log sampling probabilities; keep strata; verify with random-negative stratum |
| Public-LB overfitting | Decisions only on the frozen validation fold; public score read at most per major version |
| Candidate cap kills rare slices | Report metrics before/after caps; protect complementary channels (already specified in B4/B5) |
| SageMaker cost surprise | Spot + checkpoints + budget alarms; sample-build first (`--sample 200000` pattern); local dry runs |
| License/parameter audit failure | Only MIT/Apache/ISC/BSD packages; record license per dependency in the manifest; model ≤8B |
