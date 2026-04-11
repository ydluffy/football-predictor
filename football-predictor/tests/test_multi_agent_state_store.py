from __future__ import annotations

from config.settings import get_settings
from multi_agent.schemas import AgentName, RiskLevel, TaskKind, TaskSpec, TaskStatus, WorkflowKind
from multi_agent.state_store import SQLiteStateStore


def test_state_store_create_run_and_task(tmp_path, monkeypatch):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    store = SQLiteStateStore()
    run_id = "run-1"
    store.create_run(run_id=run_id, kind=WorkflowKind.daily_prediction)
    task = TaskSpec(task_id="t1", kind=TaskKind.validate_dataset, agent=AgentName.data_scout, risk_level=RiskLevel.low, params={})
    store.add_task(run_id=run_id, task=task)
    assert store.get_task_status("t1") == TaskStatus.planned.value
