# One-owner rule (model phase 7)

Rule: a target selected for several queries is kept only for its most probable owner (competitors: all candidate pairs, or only selected pairs), optionally with a probability margin. Policy (tau, top-k) tuned on half the queries (A) per variant, reported on the other half (B). Frozen classifier; no holdout.

## Mini-world: complete competition (10% of validation queries with all their owned targets; corpus 10x smaller, so absolute scores are optimistic)

22,050 queries, 5,853,669 pairs, 102,788 distinct targets; 100.0% of pairs are on targets that are a candidate of more than one query.

| variant | val-A | **val-B** | TP | FP | singleton FP rate |
|---|---:|---:|---:|---:|---:|
| no rule (baseline) | 0.9824 | **0.9817** | 36,852 | 380 | 4.30% |
| one owner, competitors = all candidates, margin 0.0 | 0.9872 | **0.9850** | 37,216 | 364 | 4.45% |
| one owner, competitors = all candidates, margin 0.1 | 0.9863 | **0.9840** | 37,122 | 368 | 4.76% |
| one owner, competitors = all candidates, margin 0.2 | 0.9854 | **0.9833** | 37,125 | 402 | 5.07% |
| one owner, competitors = all candidates, margin 0.3 | 0.9849 | **0.9829** | 37,125 | 423 | 5.22% |
| one owner, competitors = selected pairs, margin 0.0 | 0.9872 | **0.9852** | 37,176 | 345 | 4.15% |
| one owner, competitors = selected pairs, margin 0.1 | 0.9863 | **0.9840** | 37,140 | 372 | 4.76% |

Best by val-A: one owner, competitors = all candidates, margin 0.0.

## Sparse validation sample (9% of validation queries; most competitors absent: lower bound of the benefit)

20,000 queries, 6,340,480 pairs, 956,836 distinct targets; 98.2% of pairs are on targets that are a candidate of more than one query.

| variant | val-A | **val-B** | TP | FP | singleton FP rate |
|---|---:|---:|---:|---:|---:|
| no rule (baseline) | 0.9697 | **0.9708** | 32,833 | 462 | 4.17% |
| one owner, competitors = all candidates, margin 0.0 | 0.9703 | **0.9711** | 32,837 | 446 | 4.17% |
| one owner, competitors = all candidates, margin 0.1 | 0.9700 | **0.9710** | 32,831 | 451 | 4.17% |
| one owner, competitors = all candidates, margin 0.2 | 0.9699 | **0.9709** | 32,833 | 456 | 4.17% |
| one owner, competitors = all candidates, margin 0.3 | 0.9697 | **0.9709** | 32,833 | 460 | 4.17% |
| one owner, competitors = selected pairs, margin 0.0 | 0.9703 | **0.9711** | 32,837 | 446 | 4.17% |
| one owner, competitors = selected pairs, margin 0.1 | 0.9700 | **0.9710** | 32,831 | 451 | 4.17% |

Best by val-A: one owner, competitors = all candidates, margin 0.0.

