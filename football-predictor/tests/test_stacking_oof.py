from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

pytest = __import__("pytest")
pytest.importorskip("lightgbm")

from models.stacking_oof import (
    load_stacking_oof_bundle,
    predict_stacking_oof_proba,
    save_stacking_oof_bundle,
    train_stacking_oof,
)


def _make_xy(n: int = 60):
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


def test_train_predict_save_load_oof_bundle(tmp_path):
    X, y = _make_xy(60)
    bundle = train_stacking_oof(X, y, n_folds=3, random_state=42, lightgbm_n_estimators=20)

    proba = predict_stacking_oof_proba(bundle, X.iloc[:10])
    assert proba.shape == (10, 3)
    assert np.allclose(proba.sum(axis=1), 1.0, atol=1e-6)

    path = save_stacking_oof_bundle(bundle, Path(tmp_path) / "stacking_oof.pkl")
    loaded = load_stacking_oof_bundle(path)
    proba2 = predict_stacking_oof_proba(loaded, X.iloc[:10])
    assert proba2.shape == (10, 3)
    assert np.allclose(proba2.sum(axis=1), 1.0, atol=1e-6)


def test_train_stacking_oof_invalid_folds_raises():
    X, y = _make_xy(30)
    with pytest.raises(ValueError):
        train_stacking_oof(X, y, n_folds=1)


def test_train_stacking_oof_too_few_samples_raises():
    X = pd.DataFrame(
        {
            "norm_home": [0.1, 0.2, 0.3, 0.4, 0.5],
            "norm_draw": [0.2, 0.2, 0.2, 0.2, 0.2],
            "norm_away": [0.7, 0.6, 0.5, 0.4, 0.3],
            "odds_diff_home_away": [-1.0, -0.5, 0.0, 0.5, 1.0],
        }
    )
    y = pd.Series(["H", "D", "A", "H", "D"])
    with pytest.raises(ValueError):
        train_stacking_oof(X, y, n_folds=3)

