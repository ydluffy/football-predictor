from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from models.calibration import fit_calibrator, predict_calibrated_proba


def _make_data(n: int = 60):
    X = pd.DataFrame(
        {
            "norm_home": np.linspace(0.1, 0.8, n),
            "norm_draw": np.linspace(0.2, 0.1, n),
            "norm_away": np.linspace(0.7, 0.1, n),
            "odds_diff_home_away": np.linspace(-2.0, 2.0, n),
        }
    )
    y = pd.Series((["H", "D", "A"] * ((n // 3) + 1))[:n])
    return X, y


def test_fit_calibrator_sigmoid_and_predict_proba_sums_to_one():
    X, y = _make_data(60)
    model = Pipeline([("scaler", StandardScaler(with_mean=False)), ("clf", LogisticRegression(max_iter=1000, solver="lbfgs"))])

    calibrator = fit_calibrator(model, X, y, method="sigmoid", cv=3)
    proba = predict_calibrated_proba(calibrator, X.iloc[:10])

    assert list(proba.columns) == ["p_home", "p_draw", "p_away"]
    row_sum = proba.sum(axis=1).to_numpy()
    assert np.allclose(row_sum, 1.0)


def test_fit_calibrator_invalid_method_raises():
    X, y = _make_data(30)
    model = Pipeline([("scaler", StandardScaler(with_mean=False)), ("clf", LogisticRegression(max_iter=1000, solver="lbfgs"))])
    with pytest.raises(ValueError):
        fit_calibrator(model, X, y, method="bad")


def test_fit_calibrator_isotonic_insufficient_raises():
    X, y = _make_data(30)
    model = Pipeline([("scaler", StandardScaler(with_mean=False)), ("clf", LogisticRegression(max_iter=1000, solver="lbfgs"))])
    with pytest.raises(ValueError):
        fit_calibrator(model, X, y, method="isotonic", cv=3)


def test_fit_calibrator_accepts_lightgbm_estimator():
    pytest.importorskip("lightgbm")
    from lightgbm import LGBMClassifier

    X, y = _make_data(90)
    base = LGBMClassifier(
        objective="multiclass",
        num_class=3,
        n_estimators=40,
        learning_rate=0.1,
        random_state=42,
        n_jobs=1,
        verbose=-1,
    )
    calibrator = fit_calibrator(base, X, y, method="sigmoid", cv=3)
    proba = predict_calibrated_proba(calibrator, X.iloc[:10])
    assert np.allclose(proba.sum(axis=1).to_numpy(), 1.0)
