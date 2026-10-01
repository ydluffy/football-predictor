import importlib.util
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from research_director import quality_sidecar
from research_director.manual_schedule import TZ, ScheduleStore

spec = importlib.util.spec_from_file_location(
    "quality_worker", Path(__file__).parents[1] / "scripts/manage_research_schedule.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def test_daily_starts_at_eleven(tmp_path):
    store = ScheduleStore(tmp_path / "db")
    now = datetime(2026, 9, 28, 10, tzinfo=TZ)
    worker.seed(store, now)
    snapshot = store.inspect(now)
    assert len(snapshot["tasks"]) == 4
    assert snapshot["next_due_at"] == "2026-09-28T11:00:00+08:00"
    assert all("T11:00:00" in t["run_at"] for t in snapshot["tasks"])


def test_event_retries_are_idempotent_and_do_not_run_daily_tasks(tmp_path, monkeypatch):
    store = ScheduleStore(tmp_path / "db")
    now = datetime.now(TZ)
    store.plan("daily", "coverage_audit", now, now)
    executions = []
    monkeypatch.setattr(worker, "execute", lambda task: executions.append(task["id"]))
    first = worker.tick(store, event_id="batch-123")
    second = worker.tick(store, event_id="batch-123")
    assert len(first["executed"]) == 2
    assert second["executed"] == []
    assert "daily" not in executions
    assert len(second["event_tasks"]) == 2


def test_failed_event_does_not_automatically_retry(tmp_path, monkeypatch):
    store = ScheduleStore(tmp_path / "db")

    def fail(task):
        raise RuntimeError("invalid data")

    monkeypatch.setattr(worker, "execute", fail)
    worker.tick(store, event_id="bad-batch")
    again = worker.tick(store, event_id="bad-batch")
    assert again["executed"] == []
    assert {t["status"] for t in again["event_tasks"]} == {"failed"}


def test_sidecar_preserves_previous_failure_receipt(tmp_path, monkeypatch):
    audit = tmp_path / "audit.json"
    audit.write_text("{}", encoding="utf-8")
    result = {"executed": [], "event_tasks": [{"status": "failed"}]}
    monkeypatch.setattr(quality_sidecar.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=json.dumps(result), stderr=""))
    assert quality_sidecar.audit_after_collection(tmp_path, audit)["status"] == "failed"


def test_bad_worker_response_does_not_raise_into_import(tmp_path, monkeypatch):
    audit = tmp_path / "audit.json"
    audit.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(quality_sidecar.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout="{}", stderr=""))
    assert quality_sidecar.audit_after_collection(tmp_path, audit)["status"] == "failed"
