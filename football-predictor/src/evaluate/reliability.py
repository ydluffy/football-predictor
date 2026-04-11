from __future__ import annotations

import numpy as np
import pandas as pd

from config.settings import get_settings


def _to_class_indices(y_true) -> np.ndarray:
    y = np.asarray(y_true)
    if y.ndim != 1:
        y = y.reshape(-1)
    if y.dtype.kind in {"U", "S", "O"}:
        labels = np.char.upper(y.astype(str))
        mapping = {"H": 0, "D": 1, "A": 2}
        unknown = sorted(set(labels) - set(mapping.keys()))
        if unknown:
            raise ValueError(f"y_true 存在非法取值: {unknown}")
        return np.vectorize(mapping.get)(labels).astype(int)

    y_idx = y.astype(int)
    if np.any((y_idx < 0) | (y_idx > 2)):
        raise ValueError("y_true 仅支持 0/1/2 或 H/D/A")
    return y_idx


def _validate_proba(y_pred_proba) -> np.ndarray:
    if hasattr(y_pred_proba, "to_numpy"):
        p = y_pred_proba.to_numpy()
    else:
        p = np.asarray(y_pred_proba)

    if p.ndim != 2 or p.shape[1] != 3:
        raise ValueError("y_pred_proba 需要为形状 (n_samples, 3) 的概率矩阵")

    if not np.isfinite(p).all():
        raise ValueError("y_pred_proba 存在非有限值")

    if (p < 0.0).any() or (p > 1.0).any():
        raise ValueError("y_pred_proba 概率需在 [0,1] 区间内")

    row_sum = p.sum(axis=1)
    if not np.allclose(row_sum, 1.0, atol=1e-3):
        raise ValueError("y_pred_proba 每行概率和必须接近 1")

    return p.astype(float)


def build_reliability_table(y_true, y_pred_proba, n_bins: int = 10) -> pd.DataFrame:
    if n_bins < 2:
        raise ValueError("n_bins 至少为 2")

    y_idx = _to_class_indices(y_true)
    p = _validate_proba(y_pred_proba)

    n = len(y_idx)
    if n == 0:
        raise ValueError("空样本：y_true 无任何记录")
    if p.shape[0] != n:
        raise ValueError("y_true 与 y_pred_proba 行数不一致")

    pred_class = p.argmax(axis=1)
    conf = p.max(axis=1)
    correct = (pred_class == y_idx).astype(float)

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows = []
    for b in range(n_bins):
        lo = float(edges[b])
        hi = float(edges[b + 1])
        if b == n_bins - 1:
            mask = (conf >= lo) & (conf <= hi)
        else:
            mask = (conf >= lo) & (conf < hi)

        cnt = int(mask.sum())
        if cnt == 0:
            avg_conf = 0.0
            acc = 0.0
        else:
            avg_conf = float(conf[mask].mean())
            acc = float(correct[mask].mean())
        rows.append(
            {
                "bin_id": int(b),
                "conf_min": lo,
                "conf_max": hi,
                "avg_confidence": avg_conf,
                "empirical_accuracy": acc,
                "sample_count": cnt,
                "gap": acc - avg_conf,
            }
        )

    out = pd.DataFrame(rows)
    settings = get_settings()
    settings.artifacts_eval_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(settings.eval_reliability_table_path, index=False)
    return out
