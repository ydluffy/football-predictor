from __future__ import annotations

import numpy as np

from evaluate.metrics import _to_class_indices


def paired_bootstrap_logloss_difference(
    y_true,
    model_proba,
    reference_proba,
    *,
    n_bootstrap: int = 2000,
    random_state: int = 42,
) -> dict[str, float]:
    y_idx = _to_class_indices(y_true)
    model = np.asarray(model_proba, dtype=float)
    reference = np.asarray(reference_proba, dtype=float)
    if model.shape != reference.shape or model.shape != (len(y_idx), 3):
        raise ValueError("概率矩阵形状必须一致且为 (n_samples, 3)")
    if n_bootstrap < 100:
        raise ValueError("n_bootstrap 至少为 100")

    eps = 1e-15
    model = np.clip(model, eps, 1.0)
    reference = np.clip(reference, eps, 1.0)
    model = model / model.sum(axis=1, keepdims=True)
    reference = reference / reference.sum(axis=1, keepdims=True)
    row_index = np.arange(len(y_idx))
    diff = -np.log(model[row_index, y_idx]) + np.log(reference[row_index, y_idx])

    rng = np.random.default_rng(int(random_state))
    samples = np.empty(int(n_bootstrap), dtype=float)
    for i in range(int(n_bootstrap)):
        draw = rng.integers(0, len(diff), size=len(diff))
        samples[i] = float(diff[draw].mean())

    return {
        "mean_logloss_difference": float(diff.mean()),
        "ci95_low": float(np.quantile(samples, 0.025)),
        "ci95_high": float(np.quantile(samples, 0.975)),
        "probability_model_better": float(np.mean(samples < 0.0)),
    }
