from __future__ import annotations

import numpy as np
import pandas as pd

pytest = __import__("pytest")
pytest.importorskip("lightgbm")

from config.settings import get_settings
from models.stacking import predict_stacking_proba, save_stacking_model, train_stacking


def test_stacking_train_predict_save(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    (root / "artifacts" / "models").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    n = 60
    X = pd.DataFrame(
        {
            "norm_home": np.linspace(0.1, 0.8, n),
            "norm_draw": np.linspace(0.2, 0.1, n),
            "norm_away": np.linspace(0.7, 0.1, n),
            "odds_diff_home_away": np.linspace(-2.0, 2.0, n),
            "xg_diff": np.linspace(-1.0, 1.0, n),
            "xg_sum": np.linspace(1.0, 3.0, n),
            "injury_flag": [1 if i % 10 == 0 else 0 for i in range(n)],
            "line_move": [0.05 if i % 2 == 0 else -0.03 for i in range(n)],
        }
    )
    y = pd.Series((["H", "D", "A"] * 20)[:n])

    model = train_stacking(X, y)
    proba = predict_stacking_proba(model, X.iloc[:10])
    assert list(proba.columns) == ["p_home", "p_draw", "p_away"]
    assert np.allclose(proba.sum(axis=1).to_numpy(), 1.0)

    paths = save_stacking_model(model)
    assert settings.stacking_meta_model_path.exists()
    assert settings.stacking_logit_model_path.exists()
    assert settings.stacking_lightgbm_model_path.exists()
    assert set(paths.keys()) >= {"meta", "logit_base", "lightgbm_base"}
