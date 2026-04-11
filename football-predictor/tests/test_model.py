from __future__ import annotations

import pandas as pd

from config.settings import get_settings
from models.baseline_logit import BaselineLogitModel, load_baseline_model


def test_train_save_load_predict(tmp_path):
    root = tmp_path / "football-predictor"
    (root / "artifacts" / "models").mkdir(parents=True, exist_ok=True)

    X = pd.DataFrame(
        {
            "implied_prob_home_norm": [0.50, 0.30, 0.20, 0.70, 0.33, 0.40],
            "implied_prob_draw_norm": [0.20, 0.40, 0.30, 0.10, 0.33, 0.30],
            "implied_prob_away_norm": [0.30, 0.30, 0.50, 0.20, 0.34, 0.30],
            "odds_diff": [-2.0, 1.0, 3.0, -1.5, 0.0, 0.5],
        }
    )
    y = pd.Series(["H", "D", "A", "H", "D", "A"])

    import os

    os.environ["FOOTBALL_PREDICTOR_ROOT"] = str(root)
    get_settings.cache_clear()

    model = BaselineLogitModel().train(X, y)
    proba = model.predict_proba(X)
    assert list(proba.columns) == ["p_home", "p_draw", "p_away"]
    assert proba.shape == (len(X), 3)

    path = model.save()
    assert path.name == get_settings().baseline_model_path.name
    assert path.exists()

    loaded = load_baseline_model()
    proba2 = loaded.predict_proba(X)
    assert proba2.shape == (len(X), 3)
