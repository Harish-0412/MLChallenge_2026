# Model search `v1` (end-to-end macro-F0.5; policy tuned on val-A, reported on val-B)

73 features; train `train50k`, validation `val20k` (protocol A corpus). Selection = best val-A; quote val-B. The holdout was not used.

| variant | val-A | **val-B** | policy (tau, top-k) | singleton FP rate | TP | FP | seconds |
|---|---:|---:|---|---:|---:|---:|---:|
| xgboost depth 6 (baseline) | 0.9697 | **0.9708** | 0.5, 8 | 4.17% | 32,833 | 462 | 408 |
| xgboost depth 4 | 0.9680 | **0.9698** | 0.55, 12 | 3.45% | 32,630 | 413 | 339 |
| xgboost depth 8 | 0.9688 | **0.9700** | 0.6, 8 | 3.27% | 32,577 | 370 | 340 |
| lightgbm 63 leaves | 0.9686 | **0.9712** | 0.45, 8 | 3.63% | 32,865 | 467 | 278 |
| lightgbm 255 leaves | 0.9698 | **0.9707** | 0.6, 12 | 3.45% | 32,559 | 322 | 145 |
| xgboost depth 6, hard negatives x3 (round 2) | 0.9693 | **0.9709** | 0.6, 12 | 3.09% | 32,515 | 308 | 392 |

Winner by val-A: **lightgbm 255 leaves**.

## Calibration of the winner

| calibration | val-A | val-B | policy |
|---|---:|---:|---|
| none (raw scores) | 0.9697 | 0.9710 | {'tau': 0.55, 'top_k': 12, 'margin': 0.0} |
| Platt (sigmoid) | 0.9698 | 0.9709 | {'tau': 0.4, 'top_k': 12, 'margin': 0.0} |
| isotonic (used) | 0.9698 | 0.9707 | {'tau': 0.6, 'top_k': 12, 'margin': 0.0} |
