from __future__ import annotations

import json
from pathlib import Path

from research_director.workflows.candidate_model_upgrade_workflow import run_candidate_model_upgrade_workflow


def test_upgrade_workflow_real_uses_standardized_and_blocks_on_validation(tmp_path):
    run_dir = tmp_path / "run"
    std_path = run_dir / "std.csv"
    val_path = run_dir / "val.json"

    def run_step(step_key, agent_name, risk_level, ctx_in):
        if step_key == "data":
            return {
                "step_key": "data",
                "agent": "data_scout",
                "status": "completed",
                "summary": "ok",
                "artifacts": [],
                "metrics": {"standardized_data_path": str(std_path), "validation_path": str(val_path), "data_quality_ok": False, "required_fields_missing": ["actual_result"]},
            }
        raise AssertionError(step_key)

    out = run_candidate_model_upgrade_workflow(ctx={"data_mode": "real", "raw_matches_csv": "x", "mapping_path": "y"}, run_dir=run_dir, run_step=run_step)
    assert out["status"] == "review_required"
    assert out["decision"]["decision"] == "review_required"
    assert "data_quality_failed" in out["decision"]["gate_reasons"]
    report = json.loads((run_dir / "upgrade_report.json").read_text(encoding="utf-8"))
    assert report["standardized_data_path"] == str(std_path)
    assert report["validation_path"] == str(val_path)

