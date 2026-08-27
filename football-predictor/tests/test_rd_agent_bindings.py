from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from config.settings import get_settings
from research_director.agents.data_scout_agent import DataScoutAgent
from research_director.agents.model_trainer_agent import ModelTrainerAgent
from research_director.agents.optimizer_agent import OptimizerAgent
from research_director.agents.predictor_agent import PredictorAgent


def test_data_scout_prefers_import_real_csv_when_mapping_path_provided(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    ext = s.data_external_dir
    ext.mkdir(parents=True, exist_ok=True)
    inp = ext / "in.csv"
    pd.DataFrame(
        {
            "MatchID": ["m1"],
            "Date": ["2025-01-01"],
            "LeagueName": ["EPL"],
            "HomeTeam": ["A"],
            "AwayTeam": ["B"],
            "HomeOdds": [2.0],
            "DrawOdds": [3.0],
            "AwayOdds": [4.0],
            "Result": ["home"],
        }
    ).to_csv(inp, index=False)

    mapping = root / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "schema_version": "mapping_v1",
                "feature_version": "v3",
                "keep_unmapped": True,
                "strict": True,
                "required_standard_fields": ["match_id", "odds_home", "odds_draw", "odds_away", "actual_result"],
                "fields": {
                    "MatchID": "match_id",
                    "Date": "date",
                    "LeagueName": "league",
                    "HomeTeam": "home_team",
                    "AwayTeam": "away_team",
                    "HomeOdds": "odds_home",
                    "DrawOdds": "odds_draw",
                    "AwayOdds": "odds_away",
                    "Result": "actual_result",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    called = {}

    def _fake_run(cmd, cwd=None, env=None, capture_output=None, text=None):
        called["cmd"] = list(cmd)
        import_root = Path(str(env.get("FOOTBALL_PREDICTOR_ROOT"))) if env else root
        (import_root / "data" / "processed").mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            {
                "match_id": ["m1"],
                "odds_home": [2.0],
                "odds_draw": [3.0],
                "odds_away": [4.0],
                "actual_result": ["H"],
            }
        ).to_csv(import_root / "data" / "processed" / "real_matches_standardized.csv", index=False)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("research_director.agents.data_scout_agent.subprocess.run", _fake_run)

    agent = DataScoutAgent()
    out = agent.execute(
        context={
            "run_id": "r1",
            "run_dir": str(root / "artifacts" / "research_director" / "runs" / "r1"),
            "data_mode": "real",
            "raw_matches_csv": str(inp),
            "mapping_path": str(mapping),
            "feature_version": "v3",
        },
        gate=object(),
    )
    assert out.status == "completed"
    assert "scripts/import_real_csv.py" in " ".join(called.get("cmd", []))
    assert out.metrics.get("standardized_data_path")
    assert out.metrics.get("row_count") == 1
    assert isinstance(out.metrics.get("required_fields_missing"), list)


def test_data_scout_real_mode_missing_input_is_review_required(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    run_dir = root / "artifacts" / "research_director" / "runs" / "r0"
    agent = DataScoutAgent()
    out = agent.execute(context={"run_id": "r0", "run_dir": str(run_dir), "data_mode": "real", "feature_version": "v3"}, gate=object())
    assert out.status in {"review_required", "failed"}
    assert out.metrics.get("error_message")
    assert not (run_dir / "daily_matches.csv").exists()


def test_model_trainer_passes_use_verifier_flag(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    called = {}

    def _fake_run(cmd, cwd=None, env=None, capture_output=None, text=None):
        called["cmd"] = list(cmd)
        return SimpleNamespace(returncode=0, stdout='{"brier": 0.1, "logloss": 0.2}\n', stderr="")

    monkeypatch.setattr("research_director.agents.model_trainer_agent.subprocess.run", _fake_run)
    agent = ModelTrainerAgent()
    gate = SimpleNamespace(allow_high_risk=True)
    res = agent.execute(
        context={"run_id": "r2", "run_dir": str(root / "artifacts" / "research_director" / "runs" / "r2"), "model_type": "logit", "feature_version": "v3", "calibration": "none", "cv": "false", "use_verifier": "true", "isolate": False},
        gate=gate,
    )
    assert res.status == "completed"
    assert "--use-verifier" in called["cmd"]
    idx = called["cmd"].index("--use-verifier")
    assert called["cmd"][idx + 1] == "true"


def test_model_trainer_passes_real_data_path(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    called = {}

    def _fake_run(cmd, cwd=None, env=None, capture_output=None, text=None):
        called["cmd"] = list(cmd)
        return SimpleNamespace(returncode=0, stdout='{"brier": 0.1, "logloss": 0.2}\n', stderr="")

    monkeypatch.setattr("research_director.agents.model_trainer_agent.subprocess.run", _fake_run)
    data_path = root / "data" / "processed" / "historical.csv"
    agent = ModelTrainerAgent()
    res = agent.execute(
        context={
            "run_id": "real-train",
            "run_dir": str(root / "artifacts" / "research_director" / "runs" / "real-train"),
            "model_type": "logit",
            "feature_version": "v4",
            "matches_path": str(data_path),
            "isolate": False,
        },
        gate=SimpleNamespace(allow_high_risk=True),
    )

    assert res.status == "completed"
    idx = called["cmd"].index("--data-path")
    assert called["cmd"][idx + 1] == str(data_path)


def test_optimizer_reads_model_compare_feature_compare_and_error_analysis(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    run_dir = root / "artifacts" / "research_director" / "runs" / "r3"
    eval_dir = run_dir / "sandbox_project" / "artifacts" / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        [
            {
                "run_time": "t",
                "model_type": "lightgbm",
                "feature_version": "v3",
                "calibration_method": "none",
                "n_features": 10,
                "n_samples": 100,
                "brier": 0.18,
                "logloss": 0.9,
                "reliability_gap_mean": 0.08,
                "notes": "",
            }
        ]
    ).to_csv(eval_dir / "model_compare.csv", index=False)

    pd.DataFrame([{"run_time": "t", "feature_version": "v3", "n_features": 10, "n_samples": 100, "brier": 0.18, "logloss": 0.9}]).to_csv(eval_dir / "feature_compare.csv", index=False)

    pd.DataFrame(
        [
            {
                "match_id": "m1",
                "league": "EPL",
                "error_type": "high_confidence_error",
                "predicted_label": "H",
                "actual": "A",
                "max_proba": 0.9,
                "p_home": 0.9,
                "p_draw": 0.05,
                "p_away": 0.05,
                "risk_flags": '["line_move_risk"]',
                "manual_review_required": True,
            }
        ]
    ).to_csv(eval_dir / "error_analysis_with_risk.csv", index=False)

    agent = OptimizerAgent()
    out = agent.execute(context={"run_id": "r3", "run_dir": str(run_dir)}, gate=object())
    assert out.status == "completed"
    payload = json.loads((run_dir / "optimizer_suggestions.json").read_text(encoding="utf-8"))
    types = {x.get("type") for x in payload.get("suggestions", [])}
    assert "latest_model_compare" in types
    assert "latest_feature_compare" in types
    assert "error_type_count" in types


def test_predictor_falls_back_when_model_load_fails(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    run_dir = s.research_director_runs_dir / "r4"
    run_dir.mkdir(parents=True, exist_ok=True)
    matches = run_dir / "daily_matches.csv"
    pd.DataFrame(
        {
            "match_id": ["m1"],
            "odds_home": [2.0],
            "odds_draw": [3.0],
            "odds_away": [4.0],
        }
    ).to_csv(matches, index=False)

    bad_model = run_dir / "bad.pkl"
    bad_model.write_text("x", encoding="utf-8")

    monkeypatch.setattr("research_director.agents.predictor_agent.load_model", lambda model_type, path: (_ for _ in ()).throw(ModuleNotFoundError("No module named 'numpy._core'")))

    agent = PredictorAgent()
    out = agent.execute(
        context={"run_id": "r4", "run_dir": str(run_dir), "today_matches_path": str(matches), "model_type": "lightgbm", "feature_version": "v3", "model_path": str(bad_model)},
        gate=object(),
    )
    assert out.status == "completed"
    assert out.metrics.get("model_used") is False
    assert out.metrics.get("model_load_error")
    df_out = pd.read_csv(run_dir / "daily_predictions.csv")
    assert "prediction_source" in df_out.columns
    assert df_out.loc[0, "prediction_source"] == "odds_proxy_fallback"


def test_predictor_strict_policy_fails_when_model_load_fails(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    run_dir = s.research_director_runs_dir / "r5"
    run_dir.mkdir(parents=True, exist_ok=True)
    matches = run_dir / "daily_matches.csv"
    pd.DataFrame({"match_id": ["m1"], "odds_home": [2.0], "odds_draw": [3.0], "odds_away": [4.0]}).to_csv(matches, index=False)

    bad_model = run_dir / "bad.pkl"
    bad_model.write_text("x", encoding="utf-8")

    monkeypatch.setattr("research_director.agents.predictor_agent.load_model", lambda model_type, path: (_ for _ in ()).throw(ModuleNotFoundError("No module named 'numpy._core'")))

    agent = PredictorAgent()
    out = agent.execute(
        context={
            "run_id": "r5",
            "run_dir": str(run_dir),
            "today_matches_path": str(matches),
            "model_type": "lightgbm",
            "feature_version": "v3",
            "model_path": str(bad_model),
            "fallback_policy": "strict",
        },
        gate=object(),
    )
    assert out.status == "failed"
    assert out.metrics.get("fallback_policy") == "strict"
