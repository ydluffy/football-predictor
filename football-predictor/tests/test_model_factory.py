from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("lightgbm")

from config.settings import get_settings
from models.model_factory import load_model, predict_model_proba, save_model, train_model


def _make_xy(n: int = 30):
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


def test_model_factory_logit_train_predict_save_load(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    (root / "artifacts" / "models").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    X, y = _make_xy(30)
    model = train_model("logit", X, y)
    proba = predict_model_proba("logit", model, X.iloc[:5])
    assert list(proba.columns) == ["p_home", "p_draw", "p_away"]
    assert np.allclose(proba.sum(axis=1).to_numpy(), 1.0)

    path = save_model("logit", model, Path(root) / "artifacts" / "models" / "m.pkl")
    loaded = load_model("logit", path)
    proba2 = predict_model_proba("logit", loaded, X.iloc[:5])
    assert np.allclose(proba2.sum(axis=1).to_numpy(), 1.0)


def test_model_factory_lightgbm_train_predict_save_load(tmp_path):
    X, y = _make_xy(30)
    model = train_model("lightgbm", X, y, random_state=42)
    proba = predict_model_proba("lightgbm", model, X.iloc[:5])
    assert list(proba.columns) == ["p_home", "p_draw", "p_away"]
    assert np.allclose(proba.sum(axis=1).to_numpy(), 1.0)

    path = save_model("lightgbm", model, Path(tmp_path) / "lgbm.pkl")
    loaded = load_model("lightgbm", path)
    proba2 = predict_model_proba("lightgbm", loaded, X.iloc[:5])
    assert np.allclose(proba2.sum(axis=1).to_numpy(), 1.0)


def test_model_factory_stacking_train_predict_save_load(tmp_path):
    X, y = _make_xy(60)
    model = train_model("stacking", X, y, random_state=42)
    proba = predict_model_proba("stacking", model, X.iloc[:5])
    assert list(proba.columns) == ["p_home", "p_draw", "p_away"]
    assert np.allclose(proba.sum(axis=1).to_numpy(), 1.0)

    path = save_model("stacking", model, Path(tmp_path) / "stack.pkl")
    loaded = load_model("stacking", path)
    proba2 = predict_model_proba("stacking", loaded, X.iloc[:5])
    assert np.allclose(proba2.sum(axis=1).to_numpy(), 1.0)


def test_model_factory_stacking_oof_train_predict_save_load(tmp_path):
    X, y = _make_xy(70)
    model = train_model("stacking_oof", X, y, random_state=42, n_splits=3, lightgbm_n_estimators=20)
    proba = predict_model_proba("stacking_oof", model, X.iloc[:5])
    assert list(proba.columns) == ["p_home", "p_draw", "p_away"]
    assert np.allclose(proba.sum(axis=1).to_numpy(), 1.0)

    path = save_model("stacking_oof", model, Path(tmp_path) / "stack_oof.pkl")
    loaded = load_model("stacking_oof", path)
    proba2 = predict_model_proba("stacking_oof", loaded, X.iloc[:5])
    assert np.allclose(proba2.sum(axis=1).to_numpy(), 1.0)


def test_model_factory_invalid_model_type_raises():
    X, y = _make_xy(9)
    with pytest.raises(ValueError):
        train_model("bad", X, y)
