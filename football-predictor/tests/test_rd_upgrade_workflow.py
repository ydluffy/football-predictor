from __future__ import annotations

import json
from pathlib import Path

from config.settings import get_settings
from research_director.director import ResearchDirector


def test_candidate_model_upgrade_workflow_writes_report_and_decision(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    director = ResearchDirector()
    out = director.run("candidate_model_upgrade", context={"feature_version": "v3", "model_type": "lightgbm"})
    run_dir = Path(out["run_dir"])
    assert (run_dir / "upgrade_report.json").exists()
    assert {"status", "steps", "artifacts", "metrics", "decision"} <= set(out.keys())
    assert isinstance(out.get("decision"), dict)

    payload = json.loads((run_dir / "upgrade_report.json").read_text(encoding="utf-8"))
    assert payload["report_type"] == "candidate_model_upgrade"
    assert "decision" in payload
    assert "gate_reasons" in payload
    assert "allow_high_risk" in payload
    assert "candidate_was_registered" in payload
    assert "production_before" in payload
    assert "production_after" in payload
    assert "current_production_model" in payload
    assert "new_candidate_model" in payload

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert "registered_model_before" in manifest
    assert "registered_model_after" in manifest
