from __future__ import annotations

import json

import pandas as pd

from config.settings import get_settings
from evaluate.framework import time_series_cv_evaluate, time_split_evaluate
from ingest.load_data import load_matches_with_meta


def _make_sample_df(n: int) -> pd.DataFrame:
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


def test_load_matches_with_meta_includes_date(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    df = _make_sample_df(6)
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    loaded = load_matches_with_meta("data/raw/sample_matches.csv", extra_columns=["date"])
    assert "date" in loaded.columns
    assert pd.api.types.is_datetime64_any_dtype(loaded["date"].dtype)


def test_time_split_evaluate_writes_artifacts(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    df = _make_sample_df(30)
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    loaded = load_matches_with_meta("data/raw/sample_matches.csv", extra_columns=["date", "xg_home", "xg_away", "injury_flag", "line_move"])
    out = time_split_evaluate(loaded, feature_version="v2", calibrate="sigmoid", test_size=0.2)

    assert settings.eval_phase3_time_split_path.exists()
    assert settings.eval_phase3_reliability_path.exists()

    payload = json.loads(settings.eval_phase3_time_split_path.read_text(encoding="utf-8"))
    assert payload["eval_type"] == "time_split"
    assert payload["feature_version"] == "v2"
    assert {"brier", "logloss", "ece"} <= set(payload.keys())

    assert len(out.reliability) == 30


def test_time_series_cv_evaluate_writes_artifacts(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    df = _make_sample_df(36)
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    loaded = load_matches_with_meta("data/raw/sample_matches.csv", extra_columns=["date"])
    out = time_series_cv_evaluate(loaded, feature_version="v1", n_splits=4)

    assert settings.eval_phase3_cv_summary_path.exists()
    assert settings.eval_phase3_cv_folds_path.exists()
    assert settings.eval_phase3_reliability_path.exists()

    summary = json.loads(settings.eval_phase3_cv_summary_path.read_text(encoding="utf-8"))
    assert summary["eval_type"] == "time_series_cv"
    assert summary["feature_version"] == "v1"
    assert {"brier_mean", "logloss_mean", "ece_mean", "oof_brier", "oof_logloss", "oof_ece"} <= set(summary.keys())

    folds = pd.read_csv(settings.eval_phase3_cv_folds_path)
    assert len(folds) == 4
    assert {"fold", "brier", "logloss", "ece"} <= set(folds.columns)

    assert out.fold_metrics is not None
    assert len(out.fold_metrics) == 4
