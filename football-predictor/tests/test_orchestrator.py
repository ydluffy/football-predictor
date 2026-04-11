from __future__ import annotations

import json

import pandas as pd

from config.settings import get_settings
from orchestrator.predict_pipeline import run_pipeline


def test_run_pipeline_writes_metrics_and_appends_summary(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3", "m4", "m5", "m6"],
            "odds_home": [1.9, 2.1, 1.8, 2.5, 3.2, 2.9],
            "odds_draw": [3.2, 3.0, 3.4, 3.1, 3.0, 3.2],
            "odds_away": [4.1, 3.7, 4.5, 2.9, 2.3, 2.4],
            "actual_result": ["H", "H", "H", "D", "A", "A"],
        }
    )
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    out1 = run_pipeline(data_path="data/raw/sample_matches.csv", feature_version="v2")
    assert list(out1.columns) == ["match_id", "p_home", "p_draw", "p_away", "actual", "model_type"]

    settings = get_settings()
    assert settings.logit_model_path.exists()
    assert settings.eval_results_path.exists()
    assert settings.eval_metrics_path.exists()
    assert settings.eval_run_summary_path.exists()
    assert settings.eval_feature_compare_path.exists()
    audit_path = settings.artifacts_eval_dir / "data_flow_audit.json"
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit.get("schema_version") == "data_flow_audit_v1"
    assert isinstance(audit.get("steps"), list)

    payload = json.loads(settings.eval_metrics_path.read_text(encoding="utf-8"))
    assert {"run_time", "model_type", "model_name", "n_samples", "brier", "logloss"} <= set(payload.keys())
    assert payload["n_samples"] == len(out1)

    assert not settings.eval_verifier_results_path.exists()

    summary1 = pd.read_csv(settings.eval_run_summary_path)
    assert len(summary1) == 1
    assert {"run_time", "model_type", "model_name", "n_samples", "brier", "logloss", "feature_version"} <= set(summary1.columns)

    out2 = run_pipeline(data_path="data/raw/sample_matches.csv", feature_version="v1")
    assert len(out2) == len(out1)

    out3 = run_pipeline(data_path="data/raw/sample_matches.csv", feature_version="v3")
    assert len(out3) == len(out1)

    summary2 = pd.read_csv(settings.eval_run_summary_path)
    assert len(summary2) == 3

    compare = pd.read_csv(settings.eval_feature_compare_path)
    assert len(compare) == 3
    assert {"run_time", "model_type", "feature_version", "n_features", "n_samples", "brier", "logloss"} <= set(compare.columns)
    assert set(compare["feature_version"].astype(str)) == {"v1", "v2", "v3"}
    n_feat_v1 = int(compare.loc[compare["feature_version"] == "v1", "n_features"].iloc[0])
    n_feat_v2 = int(compare.loc[compare["feature_version"] == "v2", "n_features"].iloc[0])
    n_feat_v3 = int(compare.loc[compare["feature_version"] == "v3", "n_features"].iloc[0])
    assert n_feat_v1 < n_feat_v2
    assert n_feat_v2 < n_feat_v3


def test_run_pipeline_use_verifier_writes_verifier_results(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3", "m4", "m5"],
            "date": pd.date_range("2025-01-01", periods=5, freq="D").astype(str),
            "league": ["EPL", "EPL", "EPL", "LaLiga", "LaLiga"],
            "odds_home": [1.9, 2.1, 1.8, 2.5, 3.2],
            "odds_draw": [3.2, 3.0, 3.4, 3.1, 3.0],
            "odds_away": [4.1, 3.7, 4.5, 2.9, 2.3],
            "injury_flag": [0, 1, 0, 0, 1],
            "line_move": [0.0, 0.25, -0.05, 0.0, -0.3],
            "actual_result": ["H", "D", "A", "H", "A"],
        }
    )
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    run_pipeline(
        data_path="data/raw/sample_matches.csv",
        feature_version="v2",
        model_type="logit",
        calibration_method="none",
        use_verifier=True,
    )
    assert settings.eval_verifier_results_path.exists()
    out = pd.read_csv(settings.eval_verifier_results_path)
    assert {"match_id", "risk_flags", "source_confidence", "manual_review_required", "summary"} <= set(out.columns)

    comp = pd.read_csv(settings.eval_model_compare_path)
    assert "verifier_enabled" in comp.loc[comp["model_type"] == "logit", "notes"].astype(str).iloc[-1]


def test_run_pipeline_lightgbm_v3_runs(monkeypatch, tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("lightgbm")

    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    n = 50
    df = pd.DataFrame(
        {
            "match_id": [f"m{i}" for i in range(n)],
            "date": pd.date_range("2025-01-01", periods=n, freq="D").astype(str),
            "odds_home": [1.6 + (i % 7) * 0.1 for i in range(n)],
            "odds_draw": [3.0 + (i % 5) * 0.1 for i in range(n)],
            "odds_away": [2.2 + (i % 9) * 0.1 for i in range(n)],
            "xg_home": [1.2 + (i % 4) * 0.2 for i in range(n)],
            "xg_away": [1.0 + (i % 3) * 0.2 for i in range(n)],
            "injury_flag": [1 if i % 10 == 0 else 0 for i in range(n)],
            "line_move": [0.05 if i % 2 == 0 else -0.03 for i in range(n)],
            "actual_result": (["H", "D", "A"] * 20)[:n],
        }
    )
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    out = run_pipeline(
        data_path="data/raw/sample_matches.csv",
        feature_version="v3",
        model_type="lightgbm",
        calibration_method="none",
    )
    assert len(out) > 0
    assert settings.lightgbm_model_path.exists()


def test_model_compare_appends_and_schema_is_stable(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    n = 15
    df = pd.DataFrame(
        {
            "match_id": [f"m{i}" for i in range(n)],
            "date": pd.date_range("2025-01-01", periods=n, freq="D").astype(str),
            "odds_home": [1.9 + (i % 5) * 0.1 for i in range(n)],
            "odds_draw": [3.0 + (i % 4) * 0.1 for i in range(n)],
            "odds_away": [2.3 + (i % 6) * 0.1 for i in range(n)],
            "xg_home": [1.2 + (i % 3) * 0.2 for i in range(n)],
            "xg_away": [1.0 + (i % 3) * 0.2 for i in range(n)],
            "injury_flag": [1 if i % 7 == 0 else 0 for i in range(n)],
            "line_move": [0.05 if i % 2 == 0 else -0.03 for i in range(n)],
            "actual_result": (["H", "H", "D", "D", "A", "A"] * 3)[:n],
        }
    )
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    run_pipeline(data_path="data/raw/sample_matches.csv", feature_version="v2", model_type="logit", calibration_method="none")
    run_pipeline(data_path="data/raw/sample_matches.csv", feature_version="v2", model_type="logit", calibration_method="sigmoid")

    assert settings.eval_model_compare_path.exists()
    comp = pd.read_csv(settings.eval_model_compare_path)
    assert len(comp) == 2
    expected_cols = {
        "run_time",
        "model_type",
        "feature_version",
        "calibration_method",
        "n_features",
        "n_samples",
        "brier_raw",
        "logloss_raw",
        "brier_calibrated",
        "logloss_calibrated",
        "brier",
        "logloss",
        "reliability_gap_mean",
        "notes",
    }
    assert expected_cols <= set(comp.columns)
    assert comp["calibration_method"].astype(str).tolist() == ["none", "sigmoid"]
    assert comp["reliability_gap_mean"].notna().all()


def test_run_pipeline_stacking_prototype_writes_outputs(monkeypatch, tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("lightgbm")

    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    n = 60
    df = pd.DataFrame(
        {
            "match_id": [f"m{i}" for i in range(n)],
            "date": pd.date_range("2025-01-01", periods=n, freq="D").astype(str),
            "odds_home": [1.6 + (i % 7) * 0.1 for i in range(n)],
            "odds_draw": [3.0 + (i % 5) * 0.1 for i in range(n)],
            "odds_away": [2.2 + (i % 9) * 0.1 for i in range(n)],
            "xg_home": [1.2 + (i % 4) * 0.2 for i in range(n)],
            "xg_away": [1.0 + (i % 3) * 0.2 for i in range(n)],
            "injury_flag": [1 if i % 10 == 0 else 0 for i in range(n)],
            "line_move": [0.05 if i % 2 == 0 else -0.03 for i in range(n)],
            "actual_result": (["H", "D", "A"] * 20)[:n],
        }
    )
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    out = run_pipeline(data_path="data/raw/sample_matches.csv", feature_version="v2", model_type="stacking", calibration_method="none")
    assert list(out.columns) == ["match_id", "date", "p_home", "p_draw", "p_away", "actual", "model_type"]
    assert settings.stacking_meta_model_path.exists()
    assert not settings.eval_lightgbm_feature_importance_path.exists()

    comp = pd.read_csv(settings.eval_model_compare_path)
    assert "prototype_stacking" in comp.loc[comp["model_type"] == "stacking", "notes"].astype(str).iloc[-1]


def test_run_pipeline_stacking_oof_writes_outputs(monkeypatch, tmp_path):
    pytest = __import__("pytest")
    pytest.importorskip("lightgbm")

    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    n = 60
    df = pd.DataFrame(
        {
            "match_id": [f"m{i}" for i in range(n)],
            "date": pd.date_range("2025-01-01", periods=n, freq="D").astype(str),
            "odds_home": [1.6 + (i % 7) * 0.1 for i in range(n)],
            "odds_draw": [3.0 + (i % 5) * 0.1 for i in range(n)],
            "odds_away": [2.2 + (i % 9) * 0.1 for i in range(n)],
            "xg_home": [1.2 + (i % 4) * 0.2 for i in range(n)],
            "xg_away": [1.0 + (i % 3) * 0.2 for i in range(n)],
            "injury_flag": [1 if i % 10 == 0 else 0 for i in range(n)],
            "line_move": [0.05 if i % 2 == 0 else -0.03 for i in range(n)],
            "actual_result": (["H", "D", "A"] * 20)[:n],
        }
    )
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    out = run_pipeline(
        data_path="data/raw/sample_matches.csv",
        feature_version="v2",
        model_type="stacking_oof",
        calibration_method="none",
    )
    assert list(out.columns) == ["match_id", "date", "p_home", "p_draw", "p_away", "actual", "model_type"]
    assert settings.stacking_oof_meta_model_path.exists()

    comp = pd.read_csv(settings.eval_model_compare_path)
    assert "oof_stacking" in comp.loc[comp["model_type"] == "stacking_oof", "notes"].astype(str).iloc[-1]
