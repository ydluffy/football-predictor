from __future__ import annotations

import numpy as np
import pandas as pd

pytest = __import__("pytest")
pytest.importorskip("lightgbm")

from config.settings import get_settings
from models.gbdt_lgbm import train_lightgbm
from models.lightgbm_explain import export_lightgbm_feature_importance


def test_export_lightgbm_feature_importance_writes_file(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    n = 40
    X = pd.DataFrame(
        {
            "f1": np.linspace(0.0, 1.0, n),
            "f2": np.linspace(1.0, 0.0, n),
            "f3": np.sin(np.linspace(0.0, 3.14, n)),
        }
    )
    y = pd.Series((["H", "D", "A"] * 14)[:n])

    model = train_lightgbm(X, y, n_estimators=40)
    imp = export_lightgbm_feature_importance(model)
    assert settings.eval_lightgbm_feature_importance_path.exists()
    assert {"feature", "importance_split", "importance_gain"} <= set(imp.columns)
