from __future__ import annotations

import json
from datetime import datetime, timezone

from config.settings import get_settings
from research_director.scheduler import ResearchScheduler


def test_research_scheduler_loads_config_and_runs_interval_job(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    cfg = {
        "schema_version": "research_scheduler_config_v1",
        "jobs": [
            {
                "job_id": "job1",
                "workflow": "daily_prediction",
                "trigger": {"type": "interval", "seconds": 0},
                "model_type": "logit",
                "feature_version": "v3",
                "calibration": "none",
                "use_verifier": False,
                "data_mode": "mock",
            }
        ],
    }
    s.research_scheduler_config_path.parent.mkdir(parents=True, exist_ok=True)
    s.research_scheduler_config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    scheduler = ResearchScheduler.load_from_config()
    calls: list[tuple[str, dict]] = []

    class _Director:
        def run(self, workflow, context=None, run_id=None, resume=False):
            calls.append((workflow, dict(context or {})))
            return {"run_id": "RID", "status": "completed"}

    now = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    out = scheduler.run_pending(director=_Director(), now=now)
    assert len(out) == 1
    assert calls[0][0] == "daily_prediction"
    assert calls[0][1]["feature_version"] == "v3"
    assert s.research_scheduler_state_path.exists()
    assert s.research_scheduler_history_path.exists()


def test_research_scheduler_runs_cron_job_once_per_minute(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    cfg = {
        "schema_version": "research_scheduler_config_v1",
        "jobs": [
            {
                "job_id": "job_cron",
                "workflow": "post_match_learning",
                "trigger": {"type": "cron", "cron": "0 0 * * *"},
                "model_type": "logit",
                "feature_version": "v3",
                "calibration": "none",
                "use_verifier": False,
                "data_mode": "mock",
            }
        ],
    }
    s.research_scheduler_config_path.parent.mkdir(parents=True, exist_ok=True)
    s.research_scheduler_config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    scheduler = ResearchScheduler.load_from_config()
    calls: list[str] = []

    class _Director:
        def run(self, workflow, context=None, run_id=None, resume=False):
            calls.append(workflow)
            return {"run_id": "RID", "status": "completed"}

    t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    scheduler.run_pending(director=_Director(), now=t0)
    scheduler.run_pending(director=_Director(), now=t0)  # same minute, should not run twice
    assert calls == ["post_match_learning"]

