from __future__ import annotations

import pandas as pd

from config.settings import get_settings
from orchestrator.predict_pipeline import run_pipeline


def test_run_pipeline_writes_calibration_compare(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9"],
            "odds_home": [1.9, 2.1, 1.8, 2.5, 3.2, 2.9, 1.7, 2.4, 2.2],
            "odds_draw": [3.2, 3.0, 3.4, 3.1, 3.0, 3.2, 3.6, 3.3, 3.1],
            "odds_away": [4.1, 3.7, 4.5, 2.9, 2.3, 2.4, 5.2, 3.0, 3.4],
            "xg_home": [1.4, 1.8, 2.1, 1.2, 0.9, 1.0, 2.0, 1.3, 1.6],
            "xg_away": [0.8, 1.0, 1.2, 1.1, 1.4, 1.3, 0.9, 1.2, 1.1],
            "injury_flag": [0, 0, 0, 1, 0, 1, 0, 1, 0],
            "line_move": [0.05, 0.02, -0.08, 0.18, 0.12, 0.06, 0.02, -0.04, 0.01],
            "actual_result": ["H", "H", "H", "D", "D", "D", "A", "A", "A"],
        }
    )
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    run_pipeline(data_path="data/raw/sample_matches.csv", feature_version="v2", calibration_method="none", model_type="logit")
    assert not settings.eval_calibration_compare_path.exists()

    run_pipeline(data_path="data/raw/sample_matches.csv", feature_version="v2", calibration_method="sigmoid", model_type="logit")
    assert settings.eval_calibration_compare_path.exists()
    comp = pd.read_csv(settings.eval_calibration_compare_path)
    assert {"run_time", "model_type", "feature_version", "calibration_method", "n_samples", "brier_raw", "logloss_raw", "brier_calibrated", "logloss_calibrated"} <= set(
        comp.columns
    )
    assert set(comp["calibration_method"].astype(str)) == {"sigmoid"}
