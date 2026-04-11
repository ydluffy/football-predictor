from __future__ import annotations

import numpy as np
import pandas as pd

from config.settings import get_settings
from models.lightgbm_multiclass import LightGBMMulticlassModel, load_lgbm_model


def test_lightgbm_multiclass_train_predict_save_load(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    (root / "artifacts" / "models").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    X = pd.DataFrame(
        {
            "norm_home": np.linspace(0.1, 0.8, 30),
            "norm_draw": np.linspace(0.2, 0.1, 30),
            "norm_away": np.linspace(0.7, 0.1, 30),
            "odds_diff_home_away": np.linspace(-2.0, 2.0, 30),
        }
    )
    y = pd.Series((["H", "D", "A"] * 10)[:30])

    model = LightGBMMulticlassModel(params={"n_estimators": 50}).train(X, y)
    proba = model.predict_proba(X.iloc[:5])
    assert list(proba.columns) == ["p_home", "p_draw", "p_away"]
    assert np.allclose(proba.sum(axis=1).to_numpy(), 1.0)

    path = model.save()
    assert path.exists()

    loaded = load_lgbm_model()
    proba2 = loaded.predict_proba(X.iloc[:5])
    assert np.allclose(proba2.sum(axis=1).to_numpy(), 1.0)
