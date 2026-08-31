from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from evaluate.metrics import _to_class_indices


PROBA_COLUMNS = ["p_home", "p_draw", "p_away"]
MARKET_FEATURE_COLUMNS = {
    "implied_home",
    "implied_draw",
    "implied_away",
    "norm_home",
    "norm_draw",
    "norm_away",
    "odds_diff_home_away",
    "draw_vs_avg",
}


def select_context_features(features: pd.DataFrame) -> pd.DataFrame:
    columns = [column for column in features.columns if column not in MARKET_FEATURE_COLUMNS]
    if not columns:
        raise ValueError("no non-market context features available")
    return features[columns].copy()


def normalize_probabilities(values) -> np.ndarray:
    probabilities = np.asarray(values, dtype=float)
    if probabilities.ndim != 2 or probabilities.shape[1] != 3:
        raise ValueError("probability matrix must have shape (n_samples, 3)")
    probabilities = np.clip(probabilities, 1e-8, None)
    return probabilities / probabilities.sum(axis=1, keepdims=True)


class MarketResidualModel:
    def __init__(self, *, alpha: float = 10.0):
        if float(alpha) <= 0.0:
            raise ValueError("alpha must be positive")
        self.alpha = float(alpha)
        self.pipeline: Pipeline | None = None
        self.feature_names_: list[str] | None = None

    def train(self, X_context: pd.DataFrame, y_true, market_proba) -> "MarketResidualModel":
        if X_context.empty:
            raise ValueError("empty residual training features")
        y_idx = _to_class_indices(y_true)
        market = normalize_probabilities(market_proba)
        if len(y_idx) != len(X_context) or len(market) != len(X_context):
            raise ValueError("residual training row counts do not match")
        target = np.eye(3)[y_idx] - market
        pipeline = Pipeline(
            [
                ("scale", StandardScaler()),
                ("ridge", Ridge(alpha=self.alpha)),
            ]
        )
        pipeline.fit(X_context, target)
        self.pipeline = pipeline
        self.feature_names_ = list(X_context.columns)
        return self

    def predict_residual(self, X_context: pd.DataFrame) -> np.ndarray:
        if self.pipeline is None or self.feature_names_ is None:
            raise ValueError("residual model is not trained")
        missing = [column for column in self.feature_names_ if column not in X_context.columns]
        if missing:
            raise ValueError(f"missing residual features: {missing}")
        return np.asarray(self.pipeline.predict(X_context[self.feature_names_]), dtype=float)

    def predict_proba(self, X_context: pd.DataFrame, market_proba, *, strength: float) -> pd.DataFrame:
        if not 0.0 <= float(strength) <= 1.0:
            raise ValueError("strength must be between 0 and 1")
        market = normalize_probabilities(market_proba)
        residual = self.predict_residual(X_context)
        adjusted = normalize_probabilities(market + float(strength) * residual)
        return pd.DataFrame(adjusted, columns=PROBA_COLUMNS, index=X_context.index)
