from __future__ import annotations

import json
from pathlib import Path

from config.settings import get_settings
from research_director.director import ResearchDirector


def test_daily_prediction_workflow_creates_predictions_and_report(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    _ = get_settings()

    director = ResearchDirector()
    out = director.run("daily_prediction", context={"feature_version": "v1"})
    run_dir = Path(out["run_dir"])
    assert (run_dir / "daily_report.json").exists()
    assert out["status"] in {"completed", "failed", "retrying", "blocked"}
    assert {"status", "steps", "artifacts", "metrics", "decision"} <= set(out.keys())

    report = json.loads((run_dir / "daily_report.json").read_text(encoding="utf-8"))
    assert report["report_type"] == "daily_prediction"

    assert (run_dir / "daily_matches.csv").exists()
    assert (run_dir / "daily_predictions.csv").exists()
    assert (run_dir / "daily_verifier_results.csv").exists()
    assert (run_dir / "daily_predictions_with_risk.csv").exists()

    import pandas as pd

    preds = pd.read_csv(run_dir / "daily_predictions.csv")
    assert "prediction_source" in preds.columns
