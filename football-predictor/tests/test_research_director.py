from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config.settings import get_settings
from multi_agent.research_director import ResearchDirectorAgent
from multi_agent.schemas import WorkflowKind


def test_research_director_daily_workflow_executes_low_risk_task(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3"],
            "date": ["2025-01-01", "2025-01-02", "bad"],
            "odds_home": [2.1, 2.2, 2.0],
            "odds_draw": [3.2, 3.3, 3.1],
            "odds_away": [3.5, 3.6, 3.8],
            "actual_result": ["H", "D", "A"],
        }
    )

    rd = ResearchDirectorAgent()
    run = rd.run_workflow(WorkflowKind.daily_prediction, params={"feature_version": "v1", "df": df}, execute_low_risk=True)
    assert run.outcomes
    validation_outcomes = [o for o in run.outcomes if o.task_id.endswith(":validate_dataset")]
    assert len(validation_outcomes) == 1
    arts = validation_outcomes[0].artifacts
    assert len(arts) == 2
    payload = json.loads(Path(arts[0].path).read_text(encoding="utf-8"))
    assert payload["row_count"] == 3
