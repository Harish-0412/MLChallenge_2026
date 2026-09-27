"""Batch scoring bridge from an Arrow pair table to validated scored-pair records."""
from __future__ import annotations

from typing import Any

import numpy as np
import pyarrow as pa

from .contracts import ScoredPair
from .pair_features import FEATURE_COLUMNS, feature_matrix


def score_pair_table(table: pa.Table, model: Any, calibrator: Any | None = None) -> list[ScoredPair]:
    matrix = feature_matrix(table, getattr(model, "feature_names", FEATURE_COLUMNS))
    scores = np.asarray(model.predict_proba(matrix), dtype=np.float64)
    if calibrator is not None:
        scores = np.asarray(calibrator.predict(scores), dtype=np.float64)
    if len(scores) != table.num_rows or np.any(~np.isfinite(scores)) or np.any((scores < 0) | (scores > 1)):
        raise ValueError("model returned invalid probabilities")
    records = []
    for index, score in enumerate(scores):
        pair = ScoredPair(
            table["s1_entity_id"][index].as_py(), table["candidate_entity_id"][index].as_py(), float(score),
            table["country"][index].as_py(), table["evidence_slice"][index].as_py(),
        )
        pair.validate()
        records.append(pair)
    return records

