from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from config.settings import get_settings
from evaluate.feature_importance import build_lightgbm_importance_table


def test_build_lightgbm_importance_table_normal(monkeypatch, tmp_path):
    pytest.importorskip("lightgbm")
    from models.gbdt_lgbm import train_lightgbm

    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    X = pd.DataFrame({"f1": np.linspace(0.0, 1.0, 40), "f2": np.linspace(1.0, 0.0, 40)})
    y = pd.Series((["H", "D", "A"] * 14)[:40])
    model = train_lightgbm(X, y, n_estimators=30)

    out = build_lightgbm_importance_table(model, list(X.columns))
    assert settings.eval_lightgbm_feature_importance_path.exists()
    assert {"feature", "importance_gain", "importance_split", "rank_gain", "rank_split"} <= set(out.columns)
    assert out["importance_gain"].is_monotonic_decreasing


def test_build_lightgbm_importance_table_empty_features_raises(monkeypatch, tmp_path):
    pytest.importorskip("lightgbm")
    from models.gbdt_lgbm import train_lightgbm

    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    X = pd.DataFrame({"f1": np.linspace(0.0, 1.0, 30), "f2": np.linspace(1.0, 0.0, 30)})
    y = pd.Series((["H", "D", "A"] * 10)[:30])
    model = train_lightgbm(X, y, n_estimators=10)
    with pytest.raises(ValueError):
        build_lightgbm_importance_table(model, [])


def test_run_pipeline_logit_does_not_write_lightgbm_importance(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3", "m4", "m5", "m6"],
            "date": pd.date_range("2025-01-01", periods=6, freq="D").astype(str),
            "odds_home": [1.9, 2.1, 1.8, 2.5, 3.2, 2.9],
            "odds_draw": [3.2, 3.0, 3.4, 3.1, 3.0, 3.2],
            "odds_away": [4.1, 3.7, 4.5, 2.9, 2.3, 2.4],
            "actual_result": ["H", "H", "D", "D", "A", "A"],
        }
    )
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    from orchestrator.predict_pipeline import run_pipeline

    run_pipeline(data_path="data/raw/sample_matches.csv", model_type="logit", feature_version="v1", calibration_method="none")
    assert not settings.eval_lightgbm_feature_importance_path.exists()
