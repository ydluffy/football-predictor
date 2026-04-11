from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config.settings import get_settings
from research_director.model_registry import get_current_production_model, load_registry, mark_production, register_candidate
from research_director.workflows.candidate_model_upgrade_workflow import run_candidate_model_upgrade_workflow


def _stub_step(*, step_key: str, agent_name: str, risk_level: str, ctx_in: dict, train_metrics: dict, train_status: str = "completed") -> dict:
    if step_key == "train":
        return {"step_key": "train", "agent": "model_trainer", "status": train_status, "summary": train_status, "artifacts": [], "metrics": {"train_metrics": dict(train_metrics)}}
    if step_key == "evaluate":
        return {"step_key": "evaluate", "agent": "evaluator", "status": "completed", "summary": "ok", "artifacts": [], "metrics": {}}
    if step_key == "data":
        return {"step_key": "data", "agent": "data_scout", "status": "completed", "summary": "ok", "artifacts": [], "metrics": {}}
    raise AssertionError(step_key)


def test_upgrade_workflow_promote_candidate_updates_registry(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    old = register_candidate(
        model_type="logit",
        feature_version="v3",
        calibration_method="none",
        artifact_path=str(root / "old.pkl"),
        metrics_summary={"brier": 0.2},
        status="candidate",
        run_id="old_run",
    )
    _ = mark_production(model_id=old.model_id)
    assert get_current_production_model() is not None

    run_dir = s.research_director_runs_dir / "r1"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "sandbox_project" / "artifacts" / "models").mkdir(parents=True, exist_ok=True)
    (run_dir / "sandbox_project" / "artifacts" / "eval").mkdir(parents=True, exist_ok=True)
    (run_dir / "sandbox_project" / "artifacts" / "models" / s.logit_model_path.name).write_text("x", encoding="utf-8")
    (run_dir / "sandbox_project" / "artifacts" / "eval" / s.eval_metrics_path.name).write_text(json.dumps({"brier": 0.1}), encoding="utf-8")

    out = run_candidate_model_upgrade_workflow(
        ctx={
            "run_id": "r1",
            "model_type": "logit",
            "feature_version": "v3",
            "calibration": "none",
            "pytest_passed": True,
            "data_quality_ok": True,
            "high_confidence_errors_delta": 0,
            "current_metrics": {"brier": 0.2, "reliability_gap_mean": 0.01},
            "candidate_metrics": {"brier": 0.1, "reliability_gap_mean": 0.01},
        },
        run_dir=run_dir,
        run_step=lambda step_key, agent_name, risk_level, ctx_in: _stub_step(step_key=step_key, agent_name=agent_name, risk_level=risk_level, ctx_in=ctx_in, train_metrics={"brier": 0.1, "reliability_gap_mean": 0.01}),
    )
    assert out["decision"]["decision"] == "promote_candidate"
    reg = load_registry()
    assert reg.current_production_model is not None
    assert reg.current_production_model.status == "production"
    assert reg.current_production_model.model_id != old.model_id
    archived_old = [c for c in reg.candidate_models if c.model_id == old.model_id and c.status == "archived"]
    assert archived_old


def test_upgrade_workflow_review_required_marks_candidate(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    run_dir = s.research_director_runs_dir / "r2"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "sandbox_project" / "artifacts" / "models").mkdir(parents=True, exist_ok=True)
    (run_dir / "sandbox_project" / "artifacts" / "eval").mkdir(parents=True, exist_ok=True)
    (run_dir / "sandbox_project" / "artifacts" / "models" / s.logit_model_path.name).write_text("x", encoding="utf-8")
    (run_dir / "sandbox_project" / "artifacts" / "eval" / s.eval_metrics_path.name).write_text(json.dumps({"brier": 0.1}), encoding="utf-8")

    out = run_candidate_model_upgrade_workflow(
        ctx={
            "run_id": "r2",
            "model_type": "logit",
            "feature_version": "v3",
            "calibration": "none",
            "pytest_passed": True,
            "data_quality_ok": True,
            "high_confidence_errors_delta": 0,
            "current_metrics": {"brier": 0.2, "reliability_gap_mean": 0.01},
            "candidate_metrics": {"brier": 0.1, "reliability_gap_mean": 0.2},
        },
        run_dir=run_dir,
        run_step=lambda step_key, agent_name, risk_level, ctx_in: _stub_step(step_key=step_key, agent_name=agent_name, risk_level=risk_level, ctx_in=ctx_in, train_metrics={"brier": 0.1, "reliability_gap_mean": 0.2}),
    )
    assert out["decision"]["decision"] == "review_required"
    reg = load_registry()
    flagged = [c for c in reg.candidate_models if c.status == "review_required"]
    assert flagged


def test_upgrade_workflow_keep_current_rejects_candidate(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    run_dir = s.research_director_runs_dir / "r3"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "sandbox_project" / "artifacts" / "models").mkdir(parents=True, exist_ok=True)
    (run_dir / "sandbox_project" / "artifacts" / "eval").mkdir(parents=True, exist_ok=True)
    (run_dir / "sandbox_project" / "artifacts" / "models" / s.logit_model_path.name).write_text("x", encoding="utf-8")
    (run_dir / "sandbox_project" / "artifacts" / "eval" / s.eval_metrics_path.name).write_text(json.dumps({"brier": 0.3}), encoding="utf-8")

    out = run_candidate_model_upgrade_workflow(
        ctx={
            "run_id": "r3",
            "model_type": "logit",
            "feature_version": "v3",
            "calibration": "none",
            "pytest_passed": True,
            "data_quality_ok": True,
            "high_confidence_errors_delta": 0,
            "current_metrics": {"brier": 0.2},
            "candidate_metrics": {"brier": 0.3},
        },
        run_dir=run_dir,
        run_step=lambda step_key, agent_name, risk_level, ctx_in: _stub_step(step_key=step_key, agent_name=agent_name, risk_level=risk_level, ctx_in=ctx_in, train_metrics={"brier": 0.3}),
    )
    assert out["decision"]["decision"] == "keep_current"
    reg = load_registry()
    rejected = [c for c in reg.candidate_models if c.status == "rejected"]
    assert rejected

