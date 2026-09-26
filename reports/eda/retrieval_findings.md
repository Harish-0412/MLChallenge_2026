# Retrieval findings (B3 + B4, protocol A on the dev fold)

Full tables: `retrieval_benchmark.md` / `.json`, missed links: `retrieval_missed_pairs.csv`. Code: `src/retrieval/`, `scripts/retrieval_benchmark.py`. 10,000 deterministic dev queries (India 4,002 and US 5,998, singletons included; digest in `data/benchmarks/build_info.json`), retrieval corpus = the dev-fold targets of the query's country (3,306,833 India + 4,949,580 US, about 80% of the 10.3M training targets). No classifier and no label is involved in candidate generation.

## B3 - the exact-key baseline (deliverable)

| union of `(country, name_key)` and `(country, address_key)` | value |
|---|---:|
| micro true-link recall | **28.96%** (audit's uncapped exact-key oracle: 28.80%) |
| all-links coverage (non-singletons) | 4.48% |
| zero-candidate queries | 23.52% |
| candidates per query mean / p50 / p90 / p99 | 6.9 / 2 / 12 / 100 |
| oracle macro-F0.5 | **0.5204** (audit: 0.5188 overall; India 0.4418 vs 0.4395, US 0.5729 vs 0.5716) |
| runtime | 4 s per channel and country |

The benchmark therefore reproduces the audit's ceiling within sampling error, which is an independent check that the corpus, the fold restriction and the evaluator are right. Name-only pairs dominate (65,599 name-only, 2,924 address-only, 464 both).

## B4 - one channel at a time (sparse channels at k = 20 per channel)

| step | micro recall | all-links coverage | mean candidates | oracle macro-F0.5 |
|---|---:|---:|---:|---:|
| v1 exact keys | 28.96% | 4.48% | 6.9 | 0.5204 |
| + name_core (v2 cleaning) | 53.94% | 16.39% | 21.2 | 0.7629 |
| + address token set | 70.95% | 36.82% | 22.0 | 0.8698 |
| + name compact | 73.07% | 39.65% | 23.0 | 0.8820 |
| + name skeleton (cross-script) | 78.20% | 47.40% | 33.5 | 0.9106 |
| + three secondary keys (name + postal / number) | 78.20% | 47.40% | 33.5 | 0.9106 (**no gain**) |
| + rare name tokens (IDF postings) | 82.83% | 56.85% | 44.9 | 0.9314 |
| + name character trigrams | 84.27% | 60.32% | 55.8 | 0.9370 |
| + rare address tokens | 92.17% | 78.21% | 72.6 | 0.9698 |
| + address token bigrams | **95.70%** | **87.10%** | **85.9** (p99 223) | **0.9849** |

With k = 100 per sparse channel the union reaches 97.08% recall, 91.18% coverage and oracle 0.9900 at 310 candidates per query. Single channels alone (k = 20): address bigrams 82.1% recall (the strongest by far), rare address tokens 62.8%, name skeleton 53.3%, name compact 48.0%, name trigrams only 23.2%. Cleaning v2 is worth +25 points of recall over the v1 keys, as measured earlier on true pairs.

## What this says about the 0.95 target

* **Gate status.** The plan's retrieval gate has two parts: micro link recall >= 99% and oracle macro-F0.5 >= 0.97. On this benchmark the oracle gate is met (0.9849 at k = 20) but the recall gate is not (95.7% at k = 20, 97.1% at k = 100). Oracle is a ceiling for a perfect classifier, not a model score.
* **The classifier will carry the score.** The candidate set has about 86 candidates per query with roughly 3.9% of them true (precision proxy). To approach the oracle a model must reject ~96% of candidates without losing a true link, and F0.5 punishes every false match four times as hard as a miss. A realistic final score will be well below the 0.985 ceiling; how far is unknown until a model is trained on these candidates (B6 then the GBDT).
* **Weak slices (recall at k = 20 / k = 100).** target address missing 75.3% / 79.8%; cross-script names 87.3% / 90.3%; low name similarity 89.1% / 91.8%; weak partial evidence 78.8% / 87.1%; no shared textual evidence 28% / 46% (only 50 links). India 94.8% / 96.4% vs US 96.3% / 97.6%. The cross-script and missing-address slices are where multilingual embeddings (DGX) can add candidates.
* **Ideas that did not help.** Equality on name + postal code or name + first house number adds no recall on top of the other channels (the postal key returns any candidate for only 4.6% of queries). Character trigrams of the name are weak alone and add 1.4 points on top. Raising k from 20 to 100 on the sparse channels adds 1.4 points of recall for 3.6 times as many candidates.

## How this was verified

1. **Engine vs brute force** (`tests/test_retrieval.py`, 8 tests): equality channels with oversize-block ranking, IDF-weighted postings (candidate sets, ranks and scores), query sampling (quotas and hash order recomputed with hashlib), the evaluator's recall / coverage / zero-candidate rate / oracle (recomputed with sets and with the independent scorer), determinism, and a guard that the engine source never mentions a label.
2. **Real-data integrity checks** (all pass): every candidate target is a dev-fold target, every query a dev query, no duplicates, ranks within 1..100, no candidate crosses countries.
3. **Determinism on real data**: rebuilding the India candidates with 3 threads instead of 8 reproduced all 1,511,875 rows (channel, query, target, rank, score) exactly (`scripts/retrieval_determinism_check.py`). Scores are summed as integer micro-IDF so thread scheduling cannot change a rank.
4. **Negative control** (`scripts/retrieval_negative_control.py`): giving each India query the features of a different query drops recall from 89.80% to 0.00% (0 of 13,896 links), so recall comes from record content, not from IDs, tie-breaks or corpus order.
5. **Reconciliation with the audit**: the baseline reproduces 28.96% vs 28.80% link recall and oracle 0.5204 vs 0.5188; every link of error types 01-03 (exact keys) and 07 (equal after cleaning) is recovered, as it must be.

## Limits

* 10,000 queries (34,562 links): overall recall has a standard error of about 0.2 points; small slices (for example the 50 "no shared evidence" links) are noisy.
* Protocol A only: the corpus is the dev fold (8.3M targets, about 80% of the test-time size). The full-corpus stress test on held-out queries (protocol B) is not run yet, and no `val` or `holdout` query was used.
* France is not evaluated (no labels); the channels are country-agnostic but their thresholds (df caps) were set on India and US corpora.
* Parameters (df caps, number of rarest tokens, k) were set once from reasoning and one run, not tuned; tuning them on `dev` is a follow-up.
* The candidate cap policy for inference (total candidates per query) is not decided; the numbers above are per-channel k.
