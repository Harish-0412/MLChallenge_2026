"""Pair classifier (XGBoost), calibration and vectorised query-level decision policies with an exact macro-F0.5 evaluation.

All decision functions work on aligned numpy arrays sorted by query; ``macro_f05_from_selection`` needs the true number of links per query
(labels are used for evaluation only).
"""
import hashlib
from typing import Dict, Sequence, Tuple

import numpy as np

from .pairs import assert_model_features


def stable_bucket(key: str, salt: str, buckets: int = 100) -> int:
    return int(hashlib.sha256(f'{salt}|{key}'.encode()).hexdigest()[:8], 16) % buckets


def fit_xgb(X_fit, y_fit, X_es, y_es, seed: int = 20260926, n_jobs: int = 8, max_depth: int = 6, learning_rate: float = 0.1, n_estimators: int = 600,
            device: str = 'cpu'):
    from xgboost import XGBClassifier
    model = XGBClassifier(n_estimators=n_estimators, learning_rate=learning_rate, max_depth=max_depth, subsample=0.85, colsample_bytree=0.85, min_child_weight=5.0,
                          reg_lambda=2.0, objective='binary:logistic', eval_metric='logloss', tree_method='hist', early_stopping_rounds=30, n_jobs=n_jobs,
                          random_state=seed, device=device)
    model.fit(X_fit, y_fit, eval_set=[(X_es, y_es)], verbose=False)
    return model


def fit_isotonic(scores: np.ndarray, labels: np.ndarray):
    from sklearn.isotonic import IsotonicRegression
    return IsotonicRegression(out_of_bounds='clip', y_min=0.0, y_max=1.0).fit(scores, labels)


# ------------------------------------------------------------------------------------------------------------------- decision policies
def _boundaries(qcodes: np.ndarray) -> np.ndarray:
    return np.flatnonzero(np.r_[True, qcodes[1:] != qcodes[:-1], True])


def sort_by_query(qcodes: np.ndarray, probs: np.ndarray) -> np.ndarray:
    """Permutation ordering rows by (query, probability desc, original position)."""
    return np.lexsort((np.arange(len(probs)), -probs, qcodes))


def select_threshold(qcodes: np.ndarray, probs: np.ndarray, tau: float, top_k: int, margin: float = 0.0) -> np.ndarray:
    """Boolean selection: p >= tau, at most top_k per query, and (optionally) the best candidate must beat the second by ``margin``."""
    order = sort_by_query(qcodes, probs)
    q, p = qcodes[order], probs[order]
    b = _boundaries(q)
    rank = np.arange(len(p)) - np.repeat(b[:-1], np.diff(b))
    sel = (p >= tau) & (rank < top_k)
    if margin > 0:
        second = np.zeros(len(p))
        has2 = np.diff(b) > 1
        second_vals = np.where(has2, p[np.minimum(b[:-1] + 1, len(p) - 1)], 0.0)
        gap_ok = (p[b[:-1]] - second_vals) >= margin
        sel &= np.repeat(gap_ok, np.diff(b))
    out = np.zeros(len(p), dtype=bool)
    out[order] = sel
    return out


def select_expected_f(qcodes: np.ndarray, probs: np.ndarray, recall_est: float, top_k: int = 12, empty_bias: float = 0.0) -> np.ndarray:
    """Per query, choose the number of top candidates m (0..top_k) maximising the plug-in expected F0.5.

    S_m = sum of the m highest probabilities (expected true positives), T = S_all / recall_est (expected number of true links including those the
    retrieval missed).  E[F](m) ~ 1.25 S_m / (1.25 S_m + (m - S_m) + 0.25 (T - S_m)) for a non-empty truth; the empty prediction is worth
    P(no true link) = prod(1 - p) (+ ``empty_bias``), and a non-empty prediction is worth (1 - P(no true link)) times the ratio above.
    """
    order = sort_by_query(qcodes, probs)
    q, p = qcodes[order], probs[order]
    b = _boundaries(q)
    out = np.zeros(len(p), dtype=bool)
    for i in range(len(b) - 1):
        lo, hi = b[i], b[i + 1]
        pi = p[lo:hi]
        p_empty = float(np.prod(1.0 - pi))
        s_all = float(pi.sum())
        total = max(s_all / recall_est, 1e-9)
        m_max = min(top_k, len(pi))
        cum = np.cumsum(pi[:m_max])
        m = np.arange(1, m_max + 1)
        ratio = 1.25 * cum / (1.25 * cum + (m - cum) + 0.25 * np.maximum(total - cum, 0.0))
        value = (1.0 - p_empty) * ratio
        best = int(np.argmax(value))
        if value[best] > p_empty + empty_bias:
            out[lo:lo + best + 1] = True
    result = np.zeros(len(p), dtype=bool)
    result[order] = out
    return result


# ------------------------------------------------------------------------------------------------------------------------- evaluation
def macro_f05_from_selection(qcodes: np.ndarray, labels: np.ndarray, selected: np.ndarray, n_true_per_query: np.ndarray, per_query: bool = False):
    """Macro F0.5 over ALL queries (``n_true_per_query`` has one entry per query code 0..Q-1, singletons and zero-candidate queries included)."""
    q_total = len(n_true_per_query)
    tp = np.bincount(qcodes[selected & (labels == 1)], minlength=q_total).astype(float)
    n_sel = np.bincount(qcodes[selected], minlength=q_total).astype(float)
    fp = n_sel - tp
    fn = n_true_per_query - tp
    denom = 1.25 * tp + fp + 0.25 * fn
    f = np.where(n_true_per_query == 0, (n_sel == 0).astype(float), np.divide(1.25 * tp, denom, out=np.zeros(q_total), where=denom > 0))
    return f if per_query else float(f.mean())


def search_threshold_policy(qcodes, probs, labels, n_true, taus: Sequence[float], top_ks: Sequence[int], margins: Sequence[float] = (0.0,)) -> Tuple[Dict, float]:
    best, best_score = None, -1.0
    for tau in taus:
        for k in top_ks:
            for margin in margins:
                score = macro_f05_from_selection(qcodes, labels, select_threshold(qcodes, probs, tau, k, margin), n_true)
                if score > best_score + 1e-12:
                    best, best_score = {'tau': float(tau), 'top_k': int(k), 'margin': float(margin)}, score
    return best, best_score


__all__ = ['fit_xgb', 'fit_isotonic', 'select_threshold', 'select_expected_f', 'macro_f05_from_selection', 'search_threshold_policy', 'stable_bucket', 'assert_model_features']
