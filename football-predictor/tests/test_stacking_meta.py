from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

pytest = __import__("pytest")
pytest.importorskip("lightgbm")

from models.stacking_meta import load_stacking_bundle, predict_stacking_proba, save_stacking_bundle, train_stacking_prototype


def test_stacking_meta_train_predict_save_load(tmp_path):
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

    bundle = train_stacking_prototype(X, y, random_state=42)
    proba = predict_stacking_proba(bundle, X.iloc[:10])
    assert proba.shape == (10, 3)
    assert np.allclose(proba.sum(axis=1), 1.0)

    path = save_stacking_bundle(bundle, Path(tmp_path) / "stack.pkl")
    loaded = load_stacking_bundle(path)
    proba2 = predict_stacking_proba(loaded, X.iloc[:10])
    assert proba2.shape == (10, 3)
    assert np.allclose(proba2.sum(axis=1), 1.0)

