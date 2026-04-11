from __future__ import annotations

import json

from config.settings import get_settings
from research_director.execution_context import ExecutionContext
from research_director.state_store import ResearchStateStore


def test_execution_context_has_unique_run_id_and_json_roundtrip(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    a = ExecutionContext(workflow_name="daily_prediction")
    b = ExecutionContext(workflow_name="daily_prediction")
    assert a.run_id != b.run_id

    payload = a.to_dict()
    s = a.to_json()
    assert isinstance(payload, dict)
    assert isinstance(s, str)

    restored = ExecutionContext.model_validate_json(s)
    assert restored.run_id == a.run_id
    assert restored.workflow_name == "daily_prediction"


def test_execution_context_is_state_store_compatible(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    store = ResearchStateStore()
    ctx = ExecutionContext(workflow_name="post_match_learning", feature_version="v3", model_type="logit", use_verifier=False)
    store.create_run(run_id=ctx.run_id, workflow=ctx.workflow_name)
    store.add_step(
        run_id=ctx.run_id,
        step_id=f"{ctx.run_id}:x:1",
        agent="evaluator",
        workflow=ctx.workflow_name,
        status="planned",
        params={"execution_context": ctx.to_dict()},
    )
    steps = store.list_steps(run_id=ctx.run_id)
    assert len(steps) == 1

