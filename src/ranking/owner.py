"""One-owner postprocessing: in the labels every S2/S3 record belongs to at most one Source-1 entity (0 targets with two owners in 7,638,365 links).

A target that is selected for two queries is therefore wrong for at least one of them.  Given calibrated probabilities for all (query, target) pairs, keep a
selected pair only if its query is the target's most probable owner (optionally allowing a margin).  This is a hypothesis to benchmark, not a submission rule.
"""
import numpy as np


def competitor_max(tcodes: np.ndarray, qcodes: np.ndarray, probs: np.ndarray) -> np.ndarray:
    """For every pair: the highest probability that the same target has with a DIFFERENT query (0 if none)."""
    order = np.lexsort((-probs, tcodes))
    t, q, p = tcodes[order], qcodes[order], probs[order]
    first = np.r_[True, t[1:] != t[:-1]]
    start = np.maximum.accumulate(np.where(first, np.arange(len(t)), 0))
    top_q, top_p = q[start], p[start]
    second_start = np.minimum(start + 1, len(t) - 1)
    has_second = (second_start > start) & (t[second_start] == t)
    second_p = np.where(has_second, p[second_start], 0.0)
    comp_sorted = np.where(q == top_q, second_p, top_p)             # the best pair competes with the runner-up, everyone else with the best
    out = np.empty_like(comp_sorted)
    out[order] = comp_sorted
    return out


def apply_one_owner(selected: np.ndarray, tcodes: np.ndarray, qcodes: np.ndarray, probs: np.ndarray, margin: float = 0.0, among: str = 'all') -> np.ndarray:
    """Drop a selected pair when another query is a more probable owner of its target by more than ``margin``.

    ``among='all'``: competitors are all candidate pairs; ``among='selected'``: only competitors that were themselves selected (hard assignment).
    """
    pool = probs if among == 'all' else np.where(selected, probs, 0.0)
    comp = competitor_max(tcodes, qcodes, pool)
    return selected & ~(comp > probs + margin)


def encode_targets_slow_reference(targets: np.ndarray) -> np.ndarray:
    """Reference implementation kept only for the test that checks the fast path against it. Do not call at scale: ``np.unique`` on an
    unsorted array of Python string objects sorts with per-element Python-level comparisons, which is fine at a few million rows but can run
    for a very long time at hundreds of millions (this is what made the real test-set export appear to hang)."""
    return np.unique(targets, return_inverse=True)[1]


def encode_targets(targets: np.ndarray) -> np.ndarray:
    """Integer-code every distinct target ID, in one hashed pass (O(n) average) instead of a full comparison sort of Python strings.

    Codes are assigned in first-appearance order, not sorted order; that is fine here because ``competitor_max``/``apply_one_owner`` only
    group by equal code, never by code ordering. Uses a plain dict rather than ``pandas.factorize`` so this module has no new dependency.
    """
    codes: dict = {}
    out = np.empty(len(targets), dtype=np.int64)
    get = codes.get
    n = len(codes)
    for i, value in enumerate(targets):
        code = get(value)
        if code is None:
            code = n
            codes[value] = code
            n += 1
        out[i] = code
    return out
