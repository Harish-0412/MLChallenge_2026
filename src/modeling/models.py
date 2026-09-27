"""Common, leakage-safe adapters for XGBoost and LightGBM."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from .pair_features import FEATURE_COLUMNS, assert_safe_feature_columns
from .reproducibility import set_global_seed


class ProbabilityModel(Protocol):
    feature_names: tuple[str, ...]

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray: ...


@dataclass(frozen=True, slots=True)
class GBDTConfig:
    backend: str = "xgboost"
    seed: int = 20260926
    n_estimators: int = 500
    learning_rate: float = 0.05
    max_depth: int = 5
    subsample: float = 0.85
    colsample_bytree: float = 0.85
    min_child_weight: float = 5.0
    reg_lambda: float = 2.0
    n_jobs: int = 4
    early_stopping_rounds: int = 40
    extra_params: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TrainedGBDT:
    estimator: Any
    feature_names: tuple[str, ...]
    backend: str

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        probabilities = self.estimator.predict_proba(matrix)
        return np.asarray(probabilities[:, 1], dtype=np.float64)


def train_gbdt(
    train_matrix: np.ndarray,
    train_labels: np.ndarray,
    validation_matrix: np.ndarray,
    validation_labels: np.ndarray,
    *,
    sample_weight: np.ndarray | None = None,
    validation_weight: np.ndarray | None = None,
    feature_names: tuple[str, ...] = FEATURE_COLUMNS,
    config: GBDTConfig = GBDTConfig(),
) -> TrainedGBDT:
    names = assert_safe_feature_columns(feature_names)
    if train_matrix.shape[1] != len(names) or validation_matrix.shape[1] != len(names):
        raise ValueError("matrix width does not match feature_names")
    if set(np.unique(train_labels)) - {0, 1} or set(np.unique(validation_labels)) - {0, 1}:
        raise ValueError("GBDT labels must be binary")
    set_global_seed(config.seed)

    common = dict(
        n_estimators=config.n_estimators, learning_rate=config.learning_rate, max_depth=config.max_depth,
        subsample=config.subsample, colsample_bytree=config.colsample_bytree,
        reg_lambda=config.reg_lambda, n_jobs=config.n_jobs, random_state=config.seed,
    )
    common.update(config.extra_params)
    backend = config.backend.lower()
    if backend == "xgboost":
        from xgboost import XGBClassifier

        estimator = XGBClassifier(
            **common, min_child_weight=config.min_child_weight, objective="binary:logistic",
            eval_metric="logloss", tree_method="hist", early_stopping_rounds=config.early_stopping_rounds,
        )
        estimator.fit(
            train_matrix, train_labels, sample_weight=sample_weight,
            eval_set=[(validation_matrix, validation_labels)], sample_weight_eval_set=[validation_weight] if validation_weight is not None else None,
            verbose=False,
        )
    elif backend == "lightgbm":
        from lightgbm import LGBMClassifier, early_stopping, log_evaluation

        estimator = LGBMClassifier(
            **common, min_child_weight=config.min_child_weight, objective="binary", verbosity=-1,
            deterministic=True, force_col_wise=True,
        )
        estimator.fit(
            train_matrix, train_labels, sample_weight=sample_weight,
            eval_X=validation_matrix, eval_y=validation_labels,
            eval_sample_weight=[validation_weight] if validation_weight is not None else None,
            callbacks=[early_stopping(config.early_stopping_rounds, verbose=False), log_evaluation(period=0)],
        )
    else:
        raise ValueError(f"unsupported GBDT backend: {config.backend!r}")
    return TrainedGBDT(estimator=estimator, feature_names=names, backend=backend)
