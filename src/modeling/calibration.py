"""Probability calibration with explicit group-disjointness checks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

import numpy as np


class Calibrator(Protocol):
    def predict(self, scores: np.ndarray) -> np.ndarray: ...


@dataclass(slots=True)
class PlattCalibrator:
    model: object

    def predict(self, scores: np.ndarray) -> np.ndarray:
        values = np.asarray(scores, dtype=np.float64).reshape(-1, 1)
        return np.asarray(self.model.predict_proba(values)[:, 1], dtype=np.float64)


@dataclass(slots=True)
class IsotonicCalibrator:
    model: object

    def predict(self, scores: np.ndarray) -> np.ndarray:
        return np.asarray(self.model.predict(np.asarray(scores, dtype=np.float64)), dtype=np.float64)


def fit_calibrator(
    scores: np.ndarray,
    labels: np.ndarray,
    *,
    method: str,
    model_fit_query_ids: Iterable[str],
    calibration_query_ids: Iterable[str],
) -> Calibrator:
    overlap = set(model_fit_query_ids) & set(calibration_query_ids)
    if overlap:
        raise ValueError(f"calibration leakage: {len(overlap)} query IDs also occurred in model fitting")
    scores = np.asarray(scores, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.int8)
    if len(scores) != len(labels) or not len(scores):
        raise ValueError("calibration scores and labels must be non-empty and aligned")
    if set(np.unique(labels)) != {0, 1}:
        raise ValueError("calibration requires both classes")
    method = method.lower()
    if method == "platt":
        from sklearn.linear_model import LogisticRegression

        model = LogisticRegression(random_state=0).fit(scores.reshape(-1, 1), labels)
        return PlattCalibrator(model)
    if method == "isotonic":
        from sklearn.isotonic import IsotonicRegression

        model = IsotonicRegression(out_of_bounds="clip").fit(scores, labels)
        return IsotonicCalibrator(model)
    raise ValueError(f"unsupported calibration method: {method!r}")

