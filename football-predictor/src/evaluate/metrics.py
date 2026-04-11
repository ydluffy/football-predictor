from __future__ import annotations

import numpy as np
from sklearn.metrics import accuracy_score, log_loss, roc_auc_score


def _to_class_indices(y_true) -> np.ndarray:
    y_true_arr = np.asarray(y_true)
    if y_true_arr.ndim != 1:
        y_true_arr = y_true_arr.reshape(-1)

    if y_true_arr.dtype.kind in {"U", "S", "O"}:
        labels = np.char.upper(y_true_arr.astype(str))
        mapping = {"H": 0, "D": 1, "A": 2}
        unknown = sorted(set(labels) - set(mapping.keys()))
        if unknown:
            raise ValueError(f"y_true 存在非法取值: {unknown}")
        return np.vectorize(mapping.get)(labels).astype(int)

    y_idx = y_true_arr.astype(int)
    if np.any((y_idx < 0) | (y_idx > 2)):
        raise ValueError("y_true 仅支持 0/1/2 或 H/D/A")
    return y_idx


def classification_metrics(y_true: np.ndarray, y_prob: np.ndarray) -> dict[str, float]:
    y_true = np.asarray(y_true).astype(int)
    y_prob = np.asarray(y_prob).astype(float)
    y_pred = (y_prob >= 0.5).astype(int)

    out: dict[str, float] = {"accuracy": float(accuracy_score(y_true, y_pred))}
    if len(np.unique(y_true)) > 1:
        out["roc_auc"] = float(roc_auc_score(y_true, y_prob))
        out["log_loss"] = float(log_loss(y_true, y_prob))
    return out


def compute_metrics(y_true, y_pred) -> dict[str, float]:
    if hasattr(y_pred, "to_numpy"):
        y_pred_arr = y_pred.to_numpy()
    else:
        y_pred_arr = np.asarray(y_pred)

    if y_pred_arr.ndim != 2 or y_pred_arr.shape[1] != 3:
        raise ValueError("y_pred 需要为形状 (n_samples, 3) 的概率矩阵")

    y_idx = _to_class_indices(y_true)
    if len(y_idx) != y_pred_arr.shape[0]:
        raise ValueError("y_true 与 y_pred 行数不一致")

    p = y_pred_arr.astype(float)
    p = np.clip(p, 1e-15, 1.0)
    row_sum = p.sum(axis=1, keepdims=True)
    row_sum[row_sum == 0.0] = 1.0
    p = p / row_sum

    y_onehot = np.eye(3)[y_idx]
    brier = float(np.mean(np.sum((p - y_onehot) ** 2, axis=1)))
    ll = float(log_loss(y_idx, p, labels=[0, 1, 2]))
    return {"brier": brier, "logloss": ll}


def expected_calibration_error(y_true, y_pred, *, n_bins: int = 10) -> float:
    y_idx = _to_class_indices(y_true)
    if hasattr(y_pred, "to_numpy"):
        p = y_pred.to_numpy()
    else:
        p = np.asarray(y_pred)

    if p.ndim != 2 or p.shape[1] != 3:
        raise ValueError("y_pred 需要为形状 (n_samples, 3) 的概率矩阵")

    p = np.asarray(p, dtype=float)
    p = np.clip(p, 1e-15, 1.0)
    row_sum = p.sum(axis=1, keepdims=True)
    row_sum[row_sum == 0.0] = 1.0
    p = p / row_sum

    n = len(y_idx)
    y_onehot = np.eye(3)[y_idx]
    ece = 0.0
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    for c in range(3):
        conf = p[:, c]
        obs = y_onehot[:, c]
        for i in range(n_bins):
            lo = edges[i]
            hi = edges[i + 1]
            if i == n_bins - 1:
                mask = (conf >= lo) & (conf <= hi)
            else:
                mask = (conf >= lo) & (conf < hi)
            if not np.any(mask):
                continue
            mean_conf = float(conf[mask].mean())
            frac_pos = float(obs[mask].mean())
            ece += (mask.sum() / n) * abs(frac_pos - mean_conf)
    return float(ece / 3.0)


def reliability_table(y_true, y_pred, *, n_bins: int = 10):
    y_idx = _to_class_indices(y_true)
    if hasattr(y_pred, "to_numpy"):
        p = y_pred.to_numpy()
    else:
        p = np.asarray(y_pred)

    if p.ndim != 2 or p.shape[1] != 3:
        raise ValueError("y_pred 需要为形状 (n_samples, 3) 的概率矩阵")

    p = np.asarray(p, dtype=float)
    p = np.clip(p, 1e-15, 1.0)
    row_sum = p.sum(axis=1, keepdims=True)
    row_sum[row_sum == 0.0] = 1.0
    p = p / row_sum

    y_onehot = np.eye(3)[y_idx]
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows = []
    classes = ["H", "D", "A"]
    for c in range(3):
        conf = p[:, c]
        obs = y_onehot[:, c]
        for i in range(n_bins):
            lo = float(edges[i])
            hi = float(edges[i + 1])
            if i == n_bins - 1:
                mask = (conf >= lo) & (conf <= hi)
            else:
                mask = (conf >= lo) & (conf < hi)
            count = int(mask.sum())
            if count == 0:
                mean_conf = 0.0
                frac_pos = 0.0
            else:
                mean_conf = float(conf[mask].mean())
                frac_pos = float(obs[mask].mean())
            rows.append(
                {
                    "class": classes[c],
                    "bin_lo": lo,
                    "bin_hi": hi,
                    "count": count,
                    "mean_conf": mean_conf,
                    "frac_pos": frac_pos,
                }
            )
    return rows
