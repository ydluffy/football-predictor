from __future__ import annotations

import numpy as np
from sklearn.metrics import log_loss


def multiclass_brier_score(y_true: np.ndarray, proba: np.ndarray) -> float:
    if y_true.ndim != 1:
        raise ValueError("y_true must be 1D")
    if proba.ndim != 2:
        raise ValueError("proba must be 2D")
    n = y_true.shape[0]
    if proba.shape[0] != n:
        raise ValueError("mismatched n_samples")
    k = proba.shape[1]
    if not (0 < k):
        raise ValueError("invalid n_classes")

    y_onehot = np.zeros((n, k), dtype=float)
    y_onehot[np.arange(n), y_true] = 1.0
    return float(np.mean(np.sum((proba - y_onehot) ** 2, axis=1)))


def multiclass_logloss(y_true: np.ndarray, proba: np.ndarray) -> float:
    return float(log_loss(y_true, proba, labels=list(range(proba.shape[1]))))
