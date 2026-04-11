from __future__ import annotations

import pandas as pd

pytest = __import__("pytest")
pytest.importorskip("lightgbm")

from config.settings import get_settings
from orchestrator.predict_pipeline import run_pipeline


def test_model_compare_appends_logit_and_lightgbm(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        {
            "match_id": [f"m{i}" for i in range(30)],
            "date": pd.date_range("2025-01-01", periods=30, freq="D").astype(str),
            "odds_home": [1.6 + (i % 7) * 0.1 for i in range(30)],
            "odds_draw": [3.0 + (i % 5) * 0.1 for i in range(30)],
            "odds_away": [2.2 + (i % 9) * 0.1 for i in range(30)],
            "xg_home": [1.2 + (i % 4) * 0.2 for i in range(30)],
            "xg_away": [1.0 + (i % 3) * 0.2 for i in range(30)],
            "injury_flag": [1 if i % 10 == 0 else 0 for i in range(30)],
            "line_move": [0.05 if i % 2 == 0 else -0.03 for i in range(30)],
            "actual_result": (["H", "D", "A"] * 10)[:30],
        }
    )
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    run_pipeline(data_path="data/raw/sample_matches.csv", feature_version="v2", calibration_method="none", model_type="logit")
    run_pipeline(data_path="data/raw/sample_matches.csv", feature_version="v2", calibration_method="none", model_type="lightgbm")

    comp = pd.read_csv(settings.eval_model_compare_path)
    assert {
        "run_time",
        "model_type",
        "feature_version",
        "calibration_method",
        "n_features",
        "n_samples",
        "brier",
        "logloss",
        "reliability_gap_mean",
        "notes",
    } <= set(comp.columns)
    assert set(comp["model_type"].astype(str)) == {"logit", "lightgbm"}
