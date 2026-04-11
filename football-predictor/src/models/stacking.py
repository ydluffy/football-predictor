from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from config.settings import get_settings
from models.model_factory import predict_model_proba, save_model as save_any_model, train_model


_PROBA_COLUMNS = ["p_home", "p_draw", "p_away"]


@dataclass(frozen=True)
class StackingModel:
    base_models: dict[str, object]
    meta_model: LogisticRegression
    base_model_types: list[str]


def _stack_features(probas: list[pd.DataFrame]) -> np.ndarray:
    mats = [p[_PROBA_COLUMNS].to_numpy(dtype=float) for p in probas]
    return np.concatenate(mats, axis=1)


def stacking_features(model: StackingModel, X: pd.DataFrame) -> pd.DataFrame:
    probas = [predict_model_proba(t, model.base_models[t], X) for t in model.base_model_types]
    Z = _stack_features(probas)
    cols = []
    for t in model.base_model_types:
        for c in _PROBA_COLUMNS:
            cols.append(f"{t}_{c}")
    return pd.DataFrame(Z, index=X.index, columns=cols)


def train_stacking(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    base_model_types: list[str] | None = None,
    random_state: int = 42,
    lightgbm_n_estimators: int = 80,
) -> StackingModel:
    types = base_model_types or ["logit", "lightgbm"]
    base_models: dict[str, object] = {}
    probas = []
    for t in types:
        if t == "lightgbm":
            m = train_model(t, X, y, random_state=random_state, n_estimators=lightgbm_n_estimators)
        else:
            m = train_model(t, X, y)
        base_models[t] = m
        probas.append(predict_model_proba(t, m, X))

    Z = _stack_features(probas)
    y_clean = y.astype(str).str.upper()
    meta = LogisticRegression(max_iter=1000, solver="lbfgs", random_state=random_state)
    meta.fit(Z, y_clean)
    return StackingModel(base_models=base_models, meta_model=meta, base_model_types=types)


def predict_stacking_proba(model: StackingModel, X: pd.DataFrame) -> pd.DataFrame:
    Z = stacking_features(model, X).to_numpy(dtype=float)
    proba = model.meta_model.predict_proba(Z)
    classes = [str(c).upper() for c in model.meta_model.classes_]
    mapping = {"H": 0, "D": 1, "A": 2}
    out = pd.DataFrame(0.0, index=X.index, columns=_PROBA_COLUMNS)
    for idx, c in enumerate(classes):
        j = mapping.get(c)
        if j is not None:
            out.iloc[:, j] = proba[:, idx]
    p = out.to_numpy(dtype=float)
    p = np.clip(p, 1e-15, 1.0)
    row_sum = p.sum(axis=1, keepdims=True)
    row_sum[row_sum == 0.0] = 1.0
    out.loc[:, _PROBA_COLUMNS] = p / row_sum
    return out


def save_stacking_model(model: StackingModel) -> dict[str, Path]:
    settings = get_settings()
    settings.artifacts_models_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}
    if "logit" in model.base_models:
        paths["logit_base"] = save_any_model("logit", model.base_models["logit"], settings.stacking_logit_model_path)
    if "lightgbm" in model.base_models:
        paths["lightgbm_base"] = save_any_model("lightgbm", model.base_models["lightgbm"], settings.stacking_lightgbm_model_path)

    with settings.stacking_meta_model_path.open("wb") as f:
        pickle.dump({"meta_model": model.meta_model, "base_model_types": model.base_model_types}, f)
    paths["meta"] = settings.stacking_meta_model_path
    return paths
