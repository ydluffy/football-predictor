from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from config.settings import get_settings
from research_director.agents.data_scout_agent import DataScoutAgent
from research_director.workflows.candidate_model_upgrade_workflow import run_candidate_model_upgrade_workflow
from research_director.workflows.daily_prediction_workflow import run_daily_prediction_workflow


def test_data_scout_real_mode_requires_existing_raw_and_mapping(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    run_dir = s.research_director_runs_dir / "r1"
    agent = DataScoutAgent()
    res = agent.execute(
        context={
            "run_id": "r1",
            "run_dir": str(run_dir),
            "data_mode": "real",
            "raw_matches_csv": str(root / "missing.csv"),
            "mapping_path": str(root / "missing_mapping.json"),
            "feature_version": "v3",
        },
        gate=object(),
    )
    assert res.status in {"failed", "review_required"}
    assert res.summary in {"raw_matches_csv_not_found", "mapping_path_not_found", "mapping_path_missing"}


def test_data_scout_real_mode_collects_import_artifact_paths(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    raw = root / "data" / "external"
    raw.mkdir(parents=True, exist_ok=True)
    raw_csv = raw / "incoming.csv"
    raw_csv.write_text("x\n1\n", encoding="utf-8")
    mapping = root / "data" / "mappings" / "m.json"
    mapping.parent.mkdir(parents=True, exist_ok=True)
    mapping.write_text("{}", encoding="utf-8")

    def _fake_run(cmd, cwd=None, env=None, capture_output=None, text=None):
        import_root = Path(str(env.get("FOOTBALL_PREDICTOR_ROOT"))) if env else root
        (import_root / "data" / "processed").mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            {
                "match_id": ["m1"],
                "date": ["2025-01-01"],
                "league": ["EPL"],
                "home_team": ["A"],
                "away_team": ["B"],
                "odds_home": [2.0],
                "odds_draw": [3.0],
                "odds_away": [4.0],
                "actual_result": ["H"],
            }
        ).to_csv(import_root / "data" / "processed" / "real_matches_standardized.csv", index=False)
        (import_root / "data" / "interim").mkdir(parents=True, exist_ok=True)
        (import_root / "data" / "interim" / "imported_preview.csv").write_text("x\n", encoding="utf-8")
        (import_root / "artifacts" / "eval").mkdir(parents=True, exist_ok=True)
        (import_root / "artifacts" / "eval" / "dataset_validation.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
        (import_root / "artifacts" / "eval" / "dataset_missing_report.csv").write_text("field,exists\n", encoding="utf-8")
        (import_root / "artifacts" / "eval" / "import_summary.json").write_text(json.dumps({"input_path": "x"}), encoding="utf-8")
        (import_root / "artifacts" / "eval" / "field_mapping_report.csv").write_text("source_field,standard_field\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("research_director.agents.data_scout_agent.subprocess.run", _fake_run)

    run_dir = s.research_director_runs_dir / "r2"
    out_path = run_dir / "daily_matches.csv"
    agent = DataScoutAgent()
    res = agent.execute(
        context={
            "run_id": "r2",
            "run_dir": str(run_dir),
            "data_mode": "real",
            "raw_matches_csv": str(raw_csv),
            "mapping_path": str(mapping),
            "feature_version": "v3",
            "output_csv_path": str(out_path),
        },
        gate=object(),
    )
    assert res.status == "completed"
    assert out_path.exists()
    m = res.metrics
    assert m["standardized_data_path"] == str(out_path)
    assert Path(str(m["import_summary_path"])).exists()
    assert Path(str(m["validation_path"])).exists()
    assert Path(str(m["missing_report_path"])).exists()


def test_daily_prediction_real_mode_missing_inputs_returns_review_required(tmp_path):
    run_dir = tmp_path / "run"

    out = run_daily_prediction_workflow(
        ctx={"data_mode": "real"},
        run_dir=run_dir,
        run_step=lambda step_key, agent_name, risk_level, ctx_in: {"status": "completed"},
    )
    assert out["status"] == "review_required"
    assert out["decision"]["decision"] == "review_required"


def test_candidate_upgrade_real_mode_missing_inputs_returns_review_required(tmp_path):
    run_dir = tmp_path / "run"

    out = run_candidate_model_upgrade_workflow(
        ctx={"data_mode": "real", "raw_matches_csv": "x"},
        run_dir=run_dir,
        run_step=lambda step_key, agent_name, risk_level, ctx_in: {"status": "completed"},
    )
    assert out["status"] == "review_required"
    assert out["decision"]["decision"] == "review_required"
