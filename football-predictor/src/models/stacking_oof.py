from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

from models.baseline_logit import BaselineLogitModel
from models.gbdt_lgbm import predict_lightgbm_proba, train_lightgbm


_PROBA_COLUMNS = ["p_home", "p_draw", "p_away"]
_LABEL_TO_INDEX = {"H": 0, "D": 1, "A": 2}


@dataclass(frozen=True)
class StackingOOFBundle:
    base_models: dict[str, object]
    meta_model: LogisticRegression
    base_model_types: list[str]
    n_splits: int


def _stack_features_from_probas(probas: list[np.ndarray]) -> np.ndarray:
    return np.concatenate(probas, axis=1)


def _proba_df_for_logit(model: BaselineLogitModel, X: pd.DataFrame) -> np.ndarray:
    p = model.predict_proba(X)[_PROBA_COLUMNS].to_numpy(dtype=float)
    return p


def _oof_base_probas(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    *,
    n_splits: int,
    random_state: int,
    lightgbm_n_estimators: int,
) -> tuple[np.ndarray, list[str]]:
    n = len(X_train)
    if n_splits < 2:
        raise ValueError("OOF stacking 需要至少 2 折")
    if n <= n_splits:
        raise ValueError("样本不足：无法进行 OOF stacking")

    y_clean = y_train.astype(str).str.upper()
    invalid = sorted(set(y_clean.unique()) - set(_LABEL_TO_INDEX.keys()))
    if invalid:
        raise ValueError(f"y 存在非法取值: {invalid}")

    counts = y_clean.value_counts()
    min_count = int(counts.min()) if len(counts) else 0
    if min_count < n_splits:
        raise ValueError("样本不足：每个类别的样本数必须 >= n_folds")

    splitter = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=int(random_state))
    oof_probas: dict[str, np.ndarray] = {
        "logit": np.full((n, 3), np.nan, dtype=float),
        "lightgbm": np.full((n, 3), np.nan, dtype=float),
    }

    for train_idx, val_idx in splitter.split(X_train, y_clean):
        X_tr = X_train.iloc[train_idx]
        y_tr = y_clean.iloc[train_idx]
        X_val = X_train.iloc[val_idx]

        logit = BaselineLogitModel().train(X_tr, y_tr)
        p_logit = _proba_df_for_logit(logit, X_val)
        oof_probas["logit"][val_idx, :] = p_logit

        lgbm = train_lightgbm(X_tr, y_tr, random_state=random_state, n_estimators=lightgbm_n_estimators)
        p_lgbm = predict_lightgbm_proba(lgbm, X_val)
        oof_probas["lightgbm"][val_idx, :] = p_lgbm

    if np.isnan(oof_probas["logit"]).any() or np.isnan(oof_probas["lightgbm"]).any():
        raise ValueError("OOF 预测未覆盖全部样本")

    Z = _stack_features_from_probas([oof_probas["logit"], oof_probas["lightgbm"]])
    cols = []
    for t in ("logit", "lightgbm"):
        for c in _PROBA_COLUMNS:
            cols.append(f"{t}_{c}")
    return Z, cols


def train_stacking_oof(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    *,
    n_folds: int = 3,
    n_splits: int | None = None,
    random_state: int = 42,
    lightgbm_n_estimators: int = 80,
) -> StackingOOFBundle:
    n_use = int(n_folds if n_splits is None else n_splits)
    Z, _ = _oof_base_probas(
        X_train,
        y_train,
        n_splits=n_use,
        random_state=int(random_state),
        lightgbm_n_estimators=int(lightgbm_n_estimators),
    )

    y_clean = y_train.astype(str).str.upper()
    meta = LogisticRegression(max_iter=1000, solver="lbfgs", random_state=int(random_state))
    meta.fit(Z, y_clean)

    base_models: dict[str, object] = {}
    base_models["logit"] = BaselineLogitModel().train(X_train, y_clean)
    base_models["lightgbm"] = train_lightgbm(X_train, y_clean, random_state=int(random_state), n_estimators=int(lightgbm_n_estimators))

    return StackingOOFBundle(base_models=base_models, meta_model=meta, base_model_types=["logit", "lightgbm"], n_splits=n_use)


def stacking_oof_meta_features(bundle: StackingOOFBundle, X: pd.DataFrame) -> pd.DataFrame:
    p_logit = _proba_df_for_logit(bundle.base_models["logit"], X)
    p_lgbm = predict_lightgbm_proba(bundle.base_models["lightgbm"], X)
    Z = _stack_features_from_probas([p_logit, p_lgbm])
    cols = []
    for t in bundle.base_model_types:
        for c in _PROBA_COLUMNS:
            cols.append(f"{t}_{c}")
    return pd.DataFrame(Z, index=X.index, columns=cols)


def predict_stacking_oof_proba(bundle: StackingOOFBundle, X_test: pd.DataFrame) -> np.ndarray:
    Z = stacking_oof_meta_features(bundle, X_test).to_numpy(dtype=float)
    proba = bundle.meta_model.predict_proba(Z)
    classes = [str(c).upper() for c in bundle.meta_model.classes_]
    out = np.zeros((Z.shape[0], 3), dtype=float)
    for i, c in enumerate(classes):
        j = _LABEL_TO_INDEX.get(c)
        if j is not None:
            out[:, j] = proba[:, i]
    out = np.clip(out, 1e-15, 1.0)
    row_sum = out.sum(axis=1, keepdims=True)
    row_sum[row_sum == 0.0] = 1.0
    return out / row_sum


def save_stacking_oof_bundle(bundle: StackingOOFBundle, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("wb") as f:
        pickle.dump(bundle, f)
    return p


def load_stacking_oof_bundle(path: str | Path) -> StackingOOFBundle:
    p = Path(path)
    with p.open("rb") as f:
        obj = pickle.load(f)
    if not isinstance(obj, StackingOOFBundle):
        raise ValueError("无效 stacking_oof bundle：类型不匹配")
    return obj
