from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config.settings import get_settings
from research_director.director import ResearchDirector
from research_director.execution_log import ExecutionRecord, append_execution_record, write_latest_execution_summary


def test_execution_log_appends_jsonl_and_writes_latest(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    r1 = ExecutionRecord(
        run_id="r1",
        workflow_name="daily_prediction",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        status="completed",
        agents_called=["data_scout"],
        key_artifacts=[{"name": "daily_report", "path": "x", "artifact_type": "json"}],
        metrics_summary={"rows": 1},
        decision_result=None,
    )
    append_execution_record(r1)
    write_latest_execution_summary(r1)

    r2 = r1.model_copy(update={"run_id": "r2", "status": "failed"})
    append_execution_record(r2)
    write_latest_execution_summary(r2)

    lines = s.research_execution_history_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    obj = json.loads(lines[-1])
    assert obj["run_id"] == "r2"
    assert obj["workflow_name"] == "daily_prediction"
    assert "agents_called" in obj

    latest = json.loads(s.research_latest_execution_summary_path.read_text(encoding="utf-8"))
    assert latest["run_id"] == "r2"
    assert latest["status"] == "failed"


def test_director_writes_execution_log_even_when_failed(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    director = ResearchDirector()
    out = director.run("unknown_workflow", context={"feature_version": "v3"})
    assert out["status"] == "failed"

    assert s.research_execution_history_path.exists()
    assert s.research_latest_execution_summary_path.exists()
    last_line = s.research_execution_history_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert payload["run_id"] == out["run_id"]
    assert payload["status"] == "failed"
    assert payload["workflow_name"] == "unknown_workflow"
    assert "model_artifact_status" in payload
    assert "model_load_error" in payload
    assert "fallback_used" in payload
    assert "fallback_policy" in payload

    manifest_path = Path(out["run_dir"]) / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for k in (
        "input_data_mode",
        "input_data_paths",
        "registered_model_before",
        "registered_model_after",
        "promoted_candidate_id",
        "scheduler_triggered",
        "model_artifact_status",
        "model_load_error",
        "fallback_used",
        "fallback_policy",
    ):
        assert k in manifest
