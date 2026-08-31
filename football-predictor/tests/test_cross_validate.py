from __future__ import annotations

import pandas as pd
import pytest

from config.settings import get_settings
from evaluate.cross_validate import run_time_series_cv


def _make_df(n: int) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    labels = (["H", "D", "A"] * ((n // 3) + 1))[:n]
    return pd.DataFrame(
        {
            "match_id": [f"m{i:04d}" for i in range(n)],
            "date": dates.astype(str),
            "odds_home": [1.6 + (i % 7) * 0.1 for i in range(n)],
            "odds_draw": [3.0 + (i % 5) * 0.1 for i in range(n)],
            "odds_away": [2.2 + (i % 9) * 0.1 for i in range(n)],
            "xg_home": [1.2 + (i % 4) * 0.2 for i in range(n)],
            "xg_away": [1.0 + (i % 3) * 0.2 for i in range(n)],
            "injury_flag": [1 if i % 10 == 0 else 0 for i in range(n)],
            "line_move": [0.05 if i % 2 == 0 else -0.03 for i in range(n)],
            "actual_result": labels,
        }
    )


def test_run_time_series_cv_writes_results(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    (root / "artifacts" / "eval").mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    df = _make_df(36).sample(frac=1.0, random_state=1).reset_index(drop=True)
    out = run_time_series_cv(df, feature_version="v3", n_splits=3, model_type="logit", calibration_method="none")

    assert settings.eval_cv_results_path.exists()
    assert len(out) == 3
    assert {
        "fold",
        "train_size",
        "test_size",
        "model_type",
        "feature_version",
        "calibration_method",
        "brier",
        "logloss",
        "market_brier",
        "market_logloss",
        "brier_vs_market",
        "logloss_vs_market",
    } <= set(out.columns)
    assert out["feature_version"].unique().tolist() == ["v3"]

    assert all(out["train_size"].to_numpy() > 0)
    assert all(out["test_size"].to_numpy() > 0)
    assert all(pd.to_datetime(out["train_end_date"]) < pd.to_datetime(out["test_start_date"]))


def test_run_time_series_cv_writes_league_metrics_when_present(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    (root / "artifacts" / "eval").mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    df = _make_df(45)
    df["league"] = (["EPL", "LaLiga", "SerieA"] * 20)[: len(df)]
    df = df.sample(frac=1.0, random_state=3).reset_index(drop=True)

    out = run_time_series_cv(df, feature_version="v3", n_splits=2, model_type="logit", calibration_method="none")
    assert len(out) == 2
    assert settings.eval_cv_league_metrics_path.exists()
    league = pd.read_csv(settings.eval_cv_league_metrics_path)
    assert {"fold", "model_type", "feature_version", "league", "n_samples", "brier", "logloss"} <= set(league.columns)
    assert set(league["fold"].astype(int)) == {0, 1}


def test_run_time_series_cv_insufficient_samples_raises(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    df = _make_df(3)
    with pytest.raises(ValueError):
        run_time_series_cv(df, feature_version="v1", n_splits=3, model_type="logit", calibration_method="none")


def test_run_time_series_cv_lightgbm_basic(monkeypatch, tmp_path):
    pytest.importorskip("lightgbm")

    root = tmp_path / "football-predictor"
    (root / "artifacts" / "eval").mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    df = _make_df(60).sample(frac=1.0, random_state=2).reset_index(drop=True)
    out = run_time_series_cv(df, feature_version="v3", n_splits=2, model_type="lightgbm", calibration_method="none")
    assert settings.eval_cv_results_path.exists()
    assert len(out) == 2
    assert out["model_type"].unique().tolist() == ["lightgbm"]


def test_run_time_series_cv_keeps_same_matchday_in_one_fold(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    (root / "artifacts" / "eval").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    df = _make_df(36)
    df["date"] = pd.Series(pd.date_range("2025-01-01", periods=12, freq="D").repeat(3)).astype(str)
    out = run_time_series_cv(df, feature_version="v1", n_splits=3, model_type="logit")

    assert len(out) == 3
    assert all(pd.to_datetime(out["train_end_date"]) < pd.to_datetime(out["test_start_date"]))
    assert out["test_size"].tolist() == [9, 9, 9]
