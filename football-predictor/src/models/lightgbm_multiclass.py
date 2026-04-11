from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

from config.settings import get_settings


_LABELS = ("H", "D", "A")
_LABEL_TO_INT = {"H": 0, "D": 1, "A": 2}
_INT_TO_LABEL = {0: "H", 1: "D", 2: "A"}
_LABEL_TO_COL = {"H": "p_home", "D": "p_draw", "A": "p_away"}
_PROBA_COLUMNS = ["p_home", "p_draw", "p_away"]


@dataclass(frozen=True)
class LightGBMTrainInfo:
    feature_names: list[str]


class LightGBMMulticlassModel:
    def __init__(
        self,
        estimator: LGBMClassifier | None = None,
        feature_names: list[str] | None = None,
        *,
        params: dict[str, object] | None = None,
    ):
        self._estimator = estimator
        self.feature_names_ = feature_names
        self._params = params or {}

    @property
    def estimator(self) -> LGBMClassifier:
        if self._estimator is None:
            raise ValueError("模型未训练")
        return self._estimator

    def train(self, X: pd.DataFrame, y: pd.Series) -> "LightGBMMulticlassModel":
        if X.empty:
            raise ValueError("空数据：X 无任何记录")
        if len(X) != len(y):
            raise ValueError("X 与 y 行数不一致")

        y_clean = y.astype(str).str.upper()
        invalid = sorted(set(y_clean.unique()) - set(_LABELS))
        if invalid:
            raise ValueError(f"y 存在非法取值: {invalid}")

        y_idx = y_clean.map(_LABEL_TO_INT).astype(int)

        params = {
            "objective": "multiclass",
            "num_class": 3,
            "n_estimators": 150,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "random_state": 42,
            "n_jobs": 1,
            "verbose": -1,
        }
        params.update(self._params)
        est = LGBMClassifier(**params)
        est.fit(X, y_idx)

        self._estimator = est
        self.feature_names_ = list(X.columns)
        return self

    def predict_proba(self, X: pd.DataFrame) -> pd.DataFrame:
        est = self.estimator
        if X.empty:
            raise ValueError("空数据：X 无任何记录")

        if self.feature_names_:
            missing = [c for c in self.feature_names_ if c not in X.columns]
            if missing:
                X_use = X.copy()
                for c in missing:
                    X_use[c] = 0.0
                X_use = X_use[self.feature_names_]
            else:
                X_use = X[self.feature_names_]
        else:
            X_use = X

        proba = est.predict_proba(X_use)
        classes = list(getattr(est, "classes_", [0, 1, 2]))
        labels = [(_INT_TO_LABEL.get(int(c)) if isinstance(c, (int, np.integer)) else str(c).upper()) for c in classes]

        out = pd.DataFrame(0.0, index=X.index, columns=_PROBA_COLUMNS)
        for i, lab in enumerate(labels):
            col = _LABEL_TO_COL.get(lab)
            if col:
                out[col] = proba[:, i]

        p = out.to_numpy(dtype=float)
        p = np.clip(p, 1e-15, 1.0)
        row_sum = p.sum(axis=1, keepdims=True)
        row_sum[row_sum == 0.0] = 1.0
        p = p / row_sum
        out.loc[:, _PROBA_COLUMNS] = p
        return out

    def save(self, path: Path | None = None) -> Path:
        settings = get_settings()
        target = path if path is not None else settings.lgbm_model_path
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"estimator": self._estimator, "feature_names": self.feature_names_}
        with target.open("wb") as f:
            pickle.dump(payload, f)
        return target


def load_lgbm_model(path: Path | None = None) -> LightGBMMulticlassModel:
    settings = get_settings()
    source = path if path is not None else settings.lgbm_model_path
    with source.open("rb") as f:
        payload = pickle.load(f)
    return LightGBMMulticlassModel(estimator=payload["estimator"], feature_names=payload.get("feature_names"))
