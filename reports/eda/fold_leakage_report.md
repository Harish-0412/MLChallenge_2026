# Fold leakage and integrity report (val_v1)

20/20 checks pass.

- PASS L1 every entity appears once: (role, entity_id) is unique - 12,527,040 rows
- PASS L2 the queries are exactly the training Source-1 entities - 2,206,821
- PASS L3 the targets are exactly the training S2/S3 entities - 10,320,219
- PASS L4 fold values are dev | val | holdout only
- PASS L5 no true link crosses folds (every labeled target is in its owner's fold) - 0 violating links of 7,638,365
- PASS L6 manifest owner_id equals the ground-truth owner for every labeled target - 0 mismatches
- PASS L7 no labeled target is treated as unmatched
- PASS L8 every (country, bucket) stratum of queries has exactly the 80/10/10 floor split - 0 strata off
- PASS L9 unmatched targets have exactly the 80/10/10 floor split per (country, source) - 0 strata off
- PASS L10 an independent hashlib recomputation reproduces every query and unmatched-target fold - 0 query, 0 target differences
- PASS L11 the fold does not track the ID number (fold mean ID within 4 standard errors of the overall mean) - dev z=-0.32, holdout z=-0.03, val z=+0.93
- PASS L12 all-empty baseline on fold "dev" equals its singleton fraction - 0.0558475 (1,765,452 queries)
- PASS L12 all-empty baseline on fold "val" equals its singleton fraction - 0.0558496 (220,682 queries)
- PASS L12 all-empty baseline on fold "holdout" equals its singleton fraction - 0.0558529 (220,687 queries)
- PASS L12 all-empty baseline on fold "all" equals its singleton fraction - 0.0558482 (2,206,821 queries)
- PASS L13 all-empty baseline on the full labeled set is the documented 0.0558482
- PASS L14 the full-corpus stress sample only contains held-out (val/holdout) queries
- PASS L15 stress protocol: every group is inside one fold
- PASS L16 stress protocol: no true link crosses folds - 0 violations
- PASS L17 stress protocol: same entities as the main protocol
