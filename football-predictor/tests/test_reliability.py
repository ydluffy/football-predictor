from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from config.settings import get_settings
from evaluate.reliability import build_reliability_table


def test_build_reliability_table_normal_case(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    y_true = pd.Series(["H", "D", "A", "H"])
    proba = pd.DataFrame(
        {
            "p_home": [0.7, 0.2, 0.1, 0.6],
            "p_draw": [0.2, 0.6, 0.2, 0.3],
            "p_away": [0.1, 0.2, 0.7, 0.1],
        }
    )

    table = build_reliability_table(y_true, proba, n_bins=10)
    assert settings.eval_reliability_table_path.exists()
    assert len(table) == 10
    assert {"bin_id", "conf_min", "conf_max", "avg_confidence", "empirical_accuracy", "sample_count", "gap"} <= set(table.columns)
    assert table["sample_count"].sum() == len(y_true)


def test_build_reliability_table_empty_raises(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    y_true = pd.Series([], dtype=str)
    proba = np.zeros((0, 3))
    with pytest.raises(ValueError):
        build_reliability_table(y_true, proba)


def test_build_reliability_table_invalid_proba_raises(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    y_true = pd.Series(["H", "D"])
    proba = np.array([[0.6, 0.6, -0.2], [0.2, 0.3, 0.5]])
    with pytest.raises(ValueError):
        build_reliability_table(y_true, proba)


def test_build_reliability_table_accepts_lightgbm_proba(monkeypatch, tmp_path):
    pytest.importorskip("lightgbm")

    from models.gbdt_lgbm import predict_lightgbm_proba, train_lightgbm

    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    n = 30
    X = pd.DataFrame(
        {
            "norm_home": np.linspace(0.1, 0.8, n),
            "norm_draw": np.linspace(0.2, 0.1, n),
            "norm_away": np.linspace(0.7, 0.1, n),
            "odds_diff_home_away": np.linspace(-2.0, 2.0, n),
        }
    )
    y = pd.Series((["H", "D", "A"] * 10)[:n])
    model = train_lightgbm(X, y, n_estimators=40)
    proba = predict_lightgbm_proba(model, X.iloc[:10])

    table = build_reliability_table(y.iloc[:10], proba, n_bins=10)
    assert table["sample_count"].sum() == 10
