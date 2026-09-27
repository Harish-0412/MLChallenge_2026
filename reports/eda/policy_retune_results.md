# Policy retune (offline, on labeled full-corpus validation data)

5,000 queries, 1,540,762 candidate pairs, retrieved from the complete 10.3M-target training corpus (same density as the real test set). Policy tuned on val-A, reported on val-B; both are held-out relative to model training and calibration.

**Caveat on one-owner:** only 5,000 of the real 1,732,544 test queries are sampled here, so almost no two sampled queries compete for the same target - one-owner's benefit is structurally invisible at this scale (see the identical no-owner/with-owner scores below). The real DGX run, with all queries present, dropped 168,952 matches via one-owner; keep it on regardless of what the small-sample grid search below prefers.

| policy | val-B macro-F0.5 |
|---|---:|
| small-corpus-tuned (ranker_v1_results.json) {'tau': 0.5, 'top_k': 8, 'margin': 0.0, 'val_A': 0.9696927524581102, 'val_B': 0.9708349245320304}, no one-owner | 0.9534 |
| small-corpus-tuned (ranker_v1_results.json) {'tau': 0.5, 'top_k': 8, 'margin': 0.0, 'val_A': 0.9696927524581102, 'val_B': 0.9708349245320304}, + one-owner | 0.9534 |
| actual DGX submission default (test_export.py) {'tau': 0.7, 'top_k': 12, 'margin': 0.0}, no one-owner | 0.9576 |
| actual DGX submission default (test_export.py) {'tau': 0.7, 'top_k': 12, 'margin': 0.0}, + one-owner | 0.9576 |
| global retune {'tau': 0.7, 'top_k': 8, 'margin': 0.0, 'owner_margin': None} | **0.9576** |
| per-slice retune (top_k=8) | **0.9569** |

## Per-slice thresholds found

| evidence_slice | tau |
|---|---:|
| exact_v1_key | 0.75 |
| cleaned_equal | 0.70 |
| skeleton_or_secondary | 0.90 |
| sparse_name | 0.60 |
| sparse_address_only | 0.85 |

**Recommendation: use the global policy (tau/top_k from the global retune above) for the real submission, with one-owner kept on regardless of this search.**
