# France candidate report (unlabeled; counts only, no accuracy claim)

5,000 deterministic French test queries (of 259,452) against the 1,434,993 French test targets (S2 703,378 + S3 731,615), same channels and parameters as for India/US (the document-frequency caps were set on India/US corpora and not retuned for France). Candidates are features-only; there is no way to measure recall.

## Candidates per query

| set | mean | p50 | p90 | p99 | max | queries with none |
|---|---:|---:|---:|---:|---:|---:|
| v1 exact keys | 8.5 | 2 | 20 | 100 | 119 | 14.46% |
| union sparse k=20 | 94.1 | 76 | 167 | 239 | 302 | 0.00% |
| union sparse k=100 | 293.7 | 295 | 384 | 452 | 504 | 0.00% |
| eq_name_key | 7.9 | 2 | 19 | 100 | 100 | 19.46% |
| eq_address_key | 0.7 | 0 | 2 | 7 | 100 | 68.86% |
| eq_name_core | 20.0 | 5 | 100 | 100 | 100 | 3.84% |
| eq_name_compact | 20.3 | 5 | 100 | 100 | 100 | 3.72% |
| eq_address_tokset | 3.3 | 2 | 6 | 29 | 100 | 19.76% |
| eq_name_skeleton | 33.6 | 14 | 100 | 100 | 100 | 1.72% |
| eq_core_postal | 0.0 | 0 | 0 | 0 | 6 | 99.72% |
| eq_core_number | 2.5 | 2 | 5 | 15 | 69 | 14.78% |
| eq_skeleton_number | 3.0 | 2 | 5 | 20 | 80 | 12.02% |
| tok_name | 58.8 | 94 | 100 | 100 | 100 | 20.64% |
| tri_name | 82.3 | 100 | 100 | 100 | 100 | 17.28% |
| tok_address | 91.7 | 100 | 100 | 100 | 100 | 2.88% |
| bigram_address | 96.6 | 100 | 100 | 100 | 100 | 0.02% |

## Text coverage (share of records)

| | accented name | address missing | Indic-script name |
|---|---:|---:|---:|
| queries | 16.5% | 0.0% | 0.00% |
| targets | 24.2% | 3.0% | 0.00% |

A high zero-candidate rate for the exact-key channels is expected (labels show that only about 29% of true links share an exact key in India/US). What matters is that the union has few empty queries and a candidate count in the same range as India/US (mean 86 / p99 223 at k = 20); a large deviation would signal that a channel threshold does not transfer to France.
