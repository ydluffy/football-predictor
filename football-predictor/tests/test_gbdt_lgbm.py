from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

pytest = __import__("pytest")
pytest.importorskip("lightgbm")

from models.gbdt_lgbm import load_lightgbm_model, predict_lightgbm_proba, save_lightgbm_model, train_lightgbm


def test_lightgbm_train_predict_save_load(tmp_path):
    X = pd.DataFrame(
        {
            "norm_home": np.linspace(0.1, 0.8, 30),
            "norm_draw": np.linspace(0.2, 0.1, 30),
            "norm_away": np.linspace(0.7, 0.1, 30),
            "odds_diff_home_away": np.linspace(-2.0, 2.0, 30),
        }
    )
    y = pd.Series((["H", "D", "A"] * 10)[:30])

    model = train_lightgbm(X, y, random_state=42)
    proba = predict_lightgbm_proba(model, X.iloc[:10])
    assert proba.shape == (10, 3)
    assert np.allclose(proba.sum(axis=1), 1.0)

    path = save_lightgbm_model(model, Path(tmp_path) / "lgbm.pkl")
    assert path.exists()

    loaded = load_lightgbm_model(path)
    proba2 = predict_lightgbm_proba(loaded, X.iloc[:10])
    assert proba2.shape == (10, 3)
    assert np.allclose(proba2.sum(axis=1), 1.0)
