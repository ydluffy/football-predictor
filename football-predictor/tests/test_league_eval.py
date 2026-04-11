from __future__ import annotations

import pandas as pd
import pytest

from config.settings import get_settings
from evaluate.league_eval import evaluate_by_league
from orchestrator.predict_pipeline import run_pipeline


def test_league_metrics_written_when_league_present(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    n = 30
    df = pd.DataFrame(
        {
            "match_id": [f"m{i}" for i in range(n)],
            "date": pd.date_range("2025-01-01", periods=n, freq="D").astype(str),
            "league": ["L1" if i % 2 == 0 else "L2" for i in range(n)],
            "odds_home": [1.6 + (i % 7) * 0.1 for i in range(n)],
            "odds_draw": [3.0 + (i % 5) * 0.1 for i in range(n)],
            "odds_away": [2.2 + (i % 9) * 0.1 for i in range(n)],
            "xg_home": [1.2 + (i % 4) * 0.2 for i in range(n)],
            "xg_away": [1.0 + (i % 3) * 0.2 for i in range(n)],
            "injury_flag": [1 if i % 10 == 0 else 0 for i in range(n)],
            "line_move": [0.05 if i % 2 == 0 else -0.03 for i in range(n)],
            "actual_result": (["H", "D", "A"] * 10)[:n],
        }
    )
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    run_pipeline(data_path="data/raw/sample_matches.csv", model_type="logit", feature_version="v2", calibration_method="none")
    assert settings.eval_league_metrics_path.exists()
    league_df = pd.read_csv(settings.eval_league_metrics_path)
    assert {"run_time", "model_type", "feature_version", "calibration_method", "league", "n_samples", "brier", "logloss"} <= set(league_df.columns)
    assert set(league_df["league"].astype(str)) <= {"L1", "L2"}


def test_evaluate_by_league_normal_case():
    df = pd.DataFrame(
        {
            "league": ["L1", "L1", "L2"],
            "actual": ["H", "D", "A"],
            "p_home": [0.7, 0.2, 0.1],
            "p_draw": [0.2, 0.6, 0.2],
            "p_away": [0.1, 0.2, 0.7],
        }
    )
    out = evaluate_by_league(df)
    assert {"league", "n_samples", "brier", "logloss"} <= set(out.columns)
    assert set(out["league"].astype(str)) == {"L1", "L2"}


def test_evaluate_by_league_missing_league_raises():
    df = pd.DataFrame({"actual": ["H"], "p_home": [0.7], "p_draw": [0.2], "p_away": [0.1]})
    with pytest.raises(ValueError):
        evaluate_by_league(df)


def test_evaluate_by_league_small_sample_is_allowed():
    df = pd.DataFrame(
        {
            "league": ["L1", "L2", "L2"],
            "actual": ["H", "D", "A"],
            "p_home": [0.7, 0.2, 0.1],
            "p_draw": [0.2, 0.6, 0.2],
            "p_away": [0.1, 0.2, 0.7],
        }
    )
    out = evaluate_by_league(df)
    assert int(out.loc[out["league"] == "L1", "n_samples"].iloc[0]) == 1
