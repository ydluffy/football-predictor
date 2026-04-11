from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd


def _require_lightgbm():
    try:
        from lightgbm import LGBMClassifier
    except Exception as e:
        raise ImportError("lightgbm 不可用：请安装 lightgbm 后再使用 gbdt_lgbm 模块") from e
    return LGBMClassifier


_LABELS = ("H", "D", "A")
_LABEL_TO_INT = {"H": 0, "D": 1, "A": 2}


def train_lightgbm(X: pd.DataFrame, y: pd.Series, random_state: int = 42, *, n_estimators: int = 120):
    LGBMClassifier = _require_lightgbm()

    if X.empty:
        raise ValueError("空数据：X 无任何记录")
    if len(X) != len(y):
        raise ValueError("X 与 y 行数不一致")

    y_clean = pd.Series(y).astype(str).str.upper()
    invalid = sorted(set(y_clean.unique()) - set(_LABELS))
    if invalid:
        raise ValueError(f"y 存在非法取值: {invalid}")

    y_idx = y_clean.map(_LABEL_TO_INT).astype(int)

    model = LGBMClassifier(
        objective="multiclass",
        num_class=3,
        random_state=int(random_state),
        n_estimators=int(n_estimators),
        learning_rate=0.05,
        num_leaves=31,
        subsample=0.8,
        colsample_bytree=0.8,
        n_jobs=1,
        verbose=-1,
    )
    model.fit(X, y_idx)
    model.feature_names_ = list(getattr(X, "columns", []))
    return model


def predict_lightgbm_proba(model, X: pd.DataFrame) -> np.ndarray:
    _require_lightgbm()
    if X.empty:
        raise ValueError("空数据：X 无任何记录")

    feature_names = getattr(model, "feature_names_", None)
    if feature_names:
        missing = [c for c in feature_names if c not in X.columns]
        if missing:
            X_use = X.copy()
            for c in missing:
                X_use[c] = 0.0
            X_use = X_use[feature_names]
        else:
            X_use = X[feature_names]
    else:
        X_use = X

    proba = model.predict_proba(X_use)
    proba = np.asarray(proba, dtype=float)
    if proba.ndim != 2 or proba.shape[1] != 3:
        raise ValueError("模型输出概率维度不符合 (n_samples, 3)")

    row_sum = proba.sum(axis=1, keepdims=True)
    row_sum[row_sum == 0.0] = 1.0
    proba = proba / row_sum
    return proba


def save_lightgbm_model(model, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("wb") as f:
        pickle.dump(model, f)
    return p


def load_lightgbm_model(path: str | Path):
    p = Path(path)
    with p.open("rb") as f:
        return pickle.load(f)
