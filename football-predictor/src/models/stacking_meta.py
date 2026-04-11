from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from models.baseline_logit import BaselineLogitModel
from models.gbdt_lgbm import predict_lightgbm_proba, train_lightgbm


_PROBA_COLUMNS = ["p_home", "p_draw", "p_away"]


@dataclass(frozen=True)
class StackingBundle:
    base_models: dict[str, object]
    meta_model: LogisticRegression
    base_model_types: list[str]


def _meta_features_from_models(bundle: StackingBundle, X: pd.DataFrame) -> np.ndarray:
    mats = []
    for t in bundle.base_model_types:
        if t == "logit":
            p = bundle.base_models[t].predict_proba(X)[_PROBA_COLUMNS].to_numpy(dtype=float)
        elif t == "lightgbm":
            p = predict_lightgbm_proba(bundle.base_models[t], X)
        else:
            raise ValueError(f"不支持的 base model_type: {t}")
        mats.append(np.asarray(p, dtype=float))
    return np.concatenate(mats, axis=1)


def stacking_meta_features(bundle: StackingBundle, X: pd.DataFrame) -> pd.DataFrame:
    Z = _meta_features_from_models(bundle, X)
    cols = []
    for t in bundle.base_model_types:
        for c in _PROBA_COLUMNS:
            cols.append(f"{t}_{c}")
    return pd.DataFrame(Z, index=X.index, columns=cols)


def _proba_3class(meta: LogisticRegression, Z: np.ndarray) -> np.ndarray:
    proba = meta.predict_proba(Z)
    classes = [str(c).upper() for c in meta.classes_]
    mapping = {"H": 0, "D": 1, "A": 2}
    out = np.zeros((Z.shape[0], 3), dtype=float)
    for i, c in enumerate(classes):
        j = mapping.get(c)
        if j is not None:
            out[:, j] = proba[:, i]
    out = np.clip(out, 1e-15, 1.0)
    row_sum = out.sum(axis=1, keepdims=True)
    row_sum[row_sum == 0.0] = 1.0
    return out / row_sum


def train_stacking_prototype(X_train: pd.DataFrame, y_train: pd.Series, random_state: int = 42) -> StackingBundle:
    base_types = ["logit", "lightgbm"]

    base_models: dict[str, object] = {}
    base_models["logit"] = BaselineLogitModel().train(X_train, y_train)
    base_models["lightgbm"] = train_lightgbm(X_train, y_train, random_state=random_state, n_estimators=80)

    bundle = StackingBundle(base_models=base_models, meta_model=LogisticRegression(), base_model_types=base_types)
    Z_train = _meta_features_from_models(bundle, X_train)

    y_clean = y_train.astype(str).str.upper()
    meta = LogisticRegression(max_iter=1000, solver="lbfgs", random_state=int(random_state))
    meta.fit(Z_train, y_clean)
    return StackingBundle(base_models=base_models, meta_model=meta, base_model_types=base_types)


def predict_stacking_proba(bundle: StackingBundle, X_test: pd.DataFrame) -> np.ndarray:
    Z = _meta_features_from_models(bundle, X_test)
    return _proba_3class(bundle.meta_model, Z)


def save_stacking_bundle(bundle: StackingBundle, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("wb") as f:
        pickle.dump(bundle, f)
    return p


def load_stacking_bundle(path: str | Path) -> StackingBundle:
    p = Path(path)
    with p.open("rb") as f:
        obj = pickle.load(f)
    if not isinstance(obj, StackingBundle):
        raise ValueError("无效 stacking bundle：类型不匹配")
    return obj
