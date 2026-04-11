from __future__ import annotations

from pathlib import Path

from research_director.workflows.daily_prediction_workflow import run_daily_prediction_workflow


def test_daily_workflow_real_uses_standardized_data_path_for_downstream(tmp_path):
    run_dir = tmp_path / "run"
    std_path = run_dir / "std.csv"

    seen = {}

    def run_step(step_key, agent_name, risk_level, ctx_in):
        if step_key == "data":
            return {"step_key": "data", "agent": "data_scout", "status": "completed", "summary": "ok", "artifacts": [], "metrics": {"standardized_data_path": str(std_path)}}
        if step_key in {"features", "predict"}:
            seen[step_key] = ctx_in.get("today_matches_path")
            return {"step_key": step_key, "agent": agent_name, "status": "completed", "summary": "ok", "artifacts": [], "metrics": {}}
        if step_key == "verify":
            return {"step_key": "verify", "agent": "verifier", "status": "completed", "summary": "ok", "artifacts": [], "metrics": {}}
        raise AssertionError(step_key)

    out = run_daily_prediction_workflow(ctx={"data_mode": "real", "raw_matches_csv": "x", "mapping_path": "y", "use_verifier": True}, run_dir=run_dir, run_step=run_step)
    assert out["status"] == "completed"
    assert seen["features"] == str(std_path)
    assert seen["predict"] == str(std_path)


def test_daily_workflow_real_validation_failed_does_not_enter_predict(tmp_path):
    run_dir = tmp_path / "run"
    called = []

    def run_step(step_key, agent_name, risk_level, ctx_in):
        called.append(step_key)
        if step_key == "data":
            return {"step_key": "data", "agent": "data_scout", "status": "review_required", "summary": "required_fields_missing", "artifacts": [], "metrics": {"error_message": "bad"}}
        raise AssertionError(step_key)

    out = run_daily_prediction_workflow(ctx={"data_mode": "real", "raw_matches_csv": "x", "mapping_path": "y"}, run_dir=run_dir, run_step=run_step)
    assert out["status"] == "review_required"
    assert called == ["data"]

