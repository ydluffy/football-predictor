from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from config.settings import get_settings
from evaluate.metrics import classification_metrics


@dataclass(frozen=True)
class TrainResult:
    model: Pipeline
    metrics: dict[str, float]
    feature_names: list[str]

_LABEL_TO_COL = {"H": "p_home", "D": "p_draw", "A": "p_away"}
_PROBA_COLUMNS = ["p_home", "p_draw", "p_away"]


class BaselineLogitModel:
    def __init__(self, pipeline: Pipeline | None = None, feature_names: list[str] | None = None):
        self._pipeline = pipeline
        self.feature_names_ = feature_names

    def train(self, X: pd.DataFrame, y: pd.Series) -> "BaselineLogitModel":
        if X.empty:
            raise ValueError("空数据：X 无任何记录")
        if len(X) != len(y):
            raise ValueError("X 与 y 行数不一致")

        y_clean = y.astype(str).str.upper()
        if y_clean.nunique() < 2:
            raise ValueError("y 类别数不足（至少需要 2 类）")

        invalid = sorted(set(y_clean.unique()) - set(_LABEL_TO_COL.keys()))
        if invalid:
            raise ValueError(f"y 存在非法取值: {invalid}")

        pipeline = Pipeline(
            steps=[
                ("scaler", StandardScaler(with_mean=False)),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=1000,
                        solver="lbfgs",
                    ),
                ),
            ]
        )
        pipeline.fit(X, y_clean)

        self._pipeline = pipeline
        self.feature_names_ = list(X.columns)
        return self

    @property
    def sklearn_estimator(self) -> Pipeline:
        if self._pipeline is None:
            raise ValueError("模型未训练")
        return self._pipeline

    def predict_proba(self, X: pd.DataFrame) -> pd.DataFrame:
        if self._pipeline is None:
            raise ValueError("模型未训练")
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

        proba = self._pipeline.predict_proba(X_use)
        clf = self._pipeline.named_steps["clf"]
        classes = [str(c).upper() for c in clf.classes_]

        out = pd.DataFrame(0.0, index=X.index, columns=_PROBA_COLUMNS)
        for idx, label in enumerate(classes):
            col = _LABEL_TO_COL.get(label)
            if col:
                out[col] = proba[:, idx]
        return out

    def save(self, path: Path | None = None) -> Path:
        settings = get_settings()
        target = path if path is not None else settings.baseline_model_path
        target.parent.mkdir(parents=True, exist_ok=True)

        payload = {"pipeline": self._pipeline, "feature_names": self.feature_names_}
        with target.open("wb") as f:
            pickle.dump(payload, f)
        return target


def load_baseline_model(path: Path | None = None) -> BaselineLogitModel:
    settings = get_settings()
    source = path if path is not None else settings.baseline_model_path
    with source.open("rb") as f:
        payload = pickle.load(f)
    return BaselineLogitModel(pipeline=payload["pipeline"], feature_names=payload.get("feature_names"))


def train_baseline_logit(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    test_size: float = 0.2,
    random_state: int = 42,
) -> TrainResult:
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=random_state,
        stratify=y if y.nunique() > 1 else None,
    )

    model = Pipeline(
        steps=[
            ("scaler", StandardScaler(with_mean=False)),
            ("clf", LogisticRegression(max_iter=1000)),
        ]
    )

    model.fit(X_train, y_train)
    model.feature_names_ = list(X.columns)
    prob = model.predict_proba(X_test)[:, 1] if y_test.nunique() > 1 else np.zeros(len(y_test))
    m = classification_metrics(y_test.to_numpy(), prob)

    return TrainResult(model=model, metrics=m, feature_names=list(X.columns))


def save_model(model: Pipeline, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump(model, f)


def load_model(path: Path) -> Pipeline:
    with path.open("rb") as f:
        return pickle.load(f)
