"""Member B: labeled pair tables (B6), the pair classifier and the query-level decision policy.

Leakage rules (enforced in code and tests):
* the model matrix is built only from ``MODEL_FEATURES``; ids, fold, truth counts, labels, weights and query-level slice names are refused;
* the classifier is fitted on dev queries, calibration/early stopping on other dev queries, decision thresholds on part of the validation queries,
  and the score is reported on the remaining validation queries; the locked holdout is never read here.
"""
