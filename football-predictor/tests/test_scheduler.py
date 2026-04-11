from __future__ import annotations

import json
from datetime import datetime, timezone

from config.settings import get_settings
from research_director.scheduler import LocalScheduler, ScheduledJob


def test_local_scheduler_runs_due_jobs_and_writes_state(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    calls = []

    class _Director:
        def run(self, workflow, context=None, run_id=None, resume=False):
            calls.append((workflow, dict(context or {})))
            return {"run_id": "RID", "status": "completed"}

    sch = LocalScheduler()
    sch.add_job(ScheduledJob(job_id="j1", workflow_name="daily_prediction", interval_seconds=0, context={"feature_version": "v3"}))
    now = datetime.now(timezone.utc)
    out = sch.run_pending(director=_Director(), now=now)
    assert len(out) == 1
    assert calls[0][0] == "daily_prediction"
    assert s.research_scheduler_state_path.exists()

    payload = json.loads(s.research_scheduler_state_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "scheduler_state_v1"
    assert "j1" in payload["jobs"]
    assert s.research_scheduler_history_path.exists()

