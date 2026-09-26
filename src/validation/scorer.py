"""Dataset-level macro-F0.5 (the challenge metric), implemented twice so each can check the other.

    F0.5_i = 1.25 TP / (1.25 TP + FP + 0.25 FN)     per Source-1 entity i, averaged over EVERY required entity.
    empty truth & empty prediction = 1; empty truth & any prediction = 0; non-empty truth & empty prediction = 0.

* ``macro_f05_sets`` - reference implementation on Python sets/lists (rejects duplicate IDs, missing or extra queries).
* ``macro_f05_tables`` - the same metric in DuckDB for millions of queries (rejects duplicate prediction rows and unknown queries).
"""
import re
from typing import Dict, Iterable, Mapping, Optional

S1_RE = re.compile(r'^S1-\d+$')
TARGET_RE = re.compile(r'^S[23]-\d+$')


class ScorerInputError(ValueError):
    pass


def entity_f05(truth: set, prediction: set) -> float:
    if not truth:
        return 1.0 if not prediction else 0.0
    tp = len(truth & prediction)
    fp, fn = len(prediction - truth), len(truth - prediction)
    denominator = 1.25 * tp + fp + 0.25 * fn
    return 0.0 if denominator == 0 else 1.25 * tp / denominator


def _as_set(owner: str, values: Iterable[str], label: str) -> set:
    raw = list(values)
    if len(raw) != len(set(raw)):
        raise ScorerInputError(f'{label} for {owner} contains duplicate IDs')
    bad = [v for v in raw if not TARGET_RE.match(v)]
    if bad:
        raise ScorerInputError(f'{label} for {owner} contains invalid target IDs {bad[:3]}')
    return set(raw)


def macro_f05_sets(truth: Mapping[str, Iterable[str]], predictions: Mapping[str, Iterable[str]], required: Optional[Iterable[str]] = None) -> Dict[str, float]:
    """Reference scorer. ``required`` is the full list of Source-1 IDs being evaluated (default: the truth keys)."""
    required = set(truth if required is None else required)
    if not required:
        raise ScorerInputError('empty query set')
    if any(not S1_RE.match(q) for q in required):
        raise ScorerInputError('invalid Source-1 ID in the required set')
    if set(truth) != required:
        raise ScorerInputError('truth does not cover exactly the required queries')
    if set(predictions) != required:
        missing, extra = required - set(predictions), set(predictions) - required
        raise ScorerInputError(f'predictions must cover every required query exactly; missing={sorted(missing)[:3]} extra={sorted(extra)[:3]}')
    total, perfect, singletons, singleton_fp = 0.0, 0, 0, 0
    for q in sorted(required):
        t, p = _as_set(q, truth[q], 'truth'), _as_set(q, predictions[q], 'prediction')
        value = entity_f05(t, p)
        total += value
        perfect += value == 1.0
        if not t:
            singletons += 1
            singleton_fp += bool(p)
    n = len(required)
    return {'macro_f05': total / n, 'queries': n, 'perfect_queries': perfect, 'singletons': singletons, 'singleton_false_positives': singleton_fp}


def macro_f05_tables(con, queries: str, truth_pairs: str, prediction_pairs: str) -> Dict[str, float]:
    """DuckDB scorer.

    ``queries``           relation with column ``id`` (every Source-1 entity to score, including singletons)
    ``truth_pairs``       relation (q, t)  - positive links of those queries (other queries' rows are ignored)
    ``prediction_pairs``  relation (q, t)  - predicted links; no duplicates, only known queries
    """
    n_pred, n_unique = con.execute(f'SELECT count(*), count(DISTINCT (q, t)) FROM {prediction_pairs}').fetchone()
    if n_pred != n_unique:
        raise ScorerInputError(f'prediction pairs contain {n_pred - n_unique} duplicate rows')
    unknown = con.execute(f'SELECT count(DISTINCT q) FROM {prediction_pairs} WHERE q NOT IN (SELECT id FROM {queries})').fetchone()[0]
    if unknown:
        raise ScorerInputError(f'{unknown} predicted queries are not in the required query set')
    if con.execute(f'SELECT count(*) FROM {queries}').fetchone()[0] == 0:
        raise ScorerInputError('empty query set')
    row = con.execute(f"""
        WITH tr AS (SELECT q, t FROM {truth_pairs} WHERE q IN (SELECT id FROM {queries})),
             tn AS (SELECT q, count(*) n FROM tr GROUP BY q),
             pn AS (SELECT q, count(*) n FROM {prediction_pairs} GROUP BY q),
             hit AS (SELECT p.q, count(*) tp FROM {prediction_pairs} p JOIN tr USING (q, t) GROUP BY p.q),
             per AS (SELECT qs.id, coalesce(tn.n, 0) tn, coalesce(pn.n, 0) pn, coalesce(hit.tp, 0) tp
                     FROM {queries} qs LEFT JOIN tn ON tn.q = qs.id LEFT JOIN pn ON pn.q = qs.id LEFT JOIN hit ON hit.q = qs.id),
             sc AS (SELECT *, CASE WHEN tn = 0 THEN (pn = 0)::DOUBLE
                                   ELSE 1.25 * tp / (1.25 * tp + (pn - tp) + 0.25 * (tn - tp)) END f FROM per)
        SELECT avg(f), count(*), count(*) FILTER (WHERE f = 1.0), count(*) FILTER (WHERE tn = 0), count(*) FILTER (WHERE tn = 0 AND pn > 0) FROM sc""").fetchone()
    return {'macro_f05': row[0], 'queries': row[1], 'perfect_queries': row[2], 'singletons': row[3], 'singleton_false_positives': row[4]}
