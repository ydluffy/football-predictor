import importlib.util
import json
from datetime import datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "guard", Path(__file__).parents[1] / "scripts/next_controller_task.py"
)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_evening_cannot_skip_morning_for_review():
    task = {"key": "review", "run_at": "2026-09-05T13:00:00+08:00", "status": "scheduled"}
    assert (
        guard.next_task(datetime.fromisoformat("2026-09-04T21:20:00+08:00"), [task])["run_at"]
        == "2026-09-05T10:00:00+08:00"
    )


def test_preopen_followed_by_confirm():
    assert (
        guard.next_task(datetime.fromisoformat("2026-09-04T10:10:00+08:00"), [])["purpose"]
        == "开售确认"
    )


def test_midday_review_preserved():
    assert (
        guard.next_task(datetime.fromisoformat("2026-09-04T12:30:00+08:00"), [])["purpose"]
        == "昨日复盘"
    )


def test_earlier_dynamic_task_wins_and_expired_is_ignored():
    tasks = [
        {
            "key": "final",
            "run_at": "2026-09-04T14:00:00+08:00",
            "hard_lock": "2026-09-04T14:45:00+08:00",
            "status": "scheduled",
        }
    ]
    assert (
        guard.next_task(datetime.fromisoformat("2026-09-04T13:20:00+08:00"), tasks)["key"]
        == "final"
    )
    assert guard.next_task(datetime.fromisoformat("2026-09-04T15:00:00+08:00"), tasks)["purpose"] == "预扫描"


def test_weekday_evening_fallback_after_review():
    tasks = [{
        "key": "late-final", "sales_day": "2026-09-14",
        "run_at": "2026-09-14T22:00:00+08:00", "hard_lock": "2026-09-14T22:45:00+08:00",
        "status": "scheduled",
    }]
    selected = guard.next_task(datetime.fromisoformat("2026-09-14T13:30:00+08:00"), tasks)
    assert selected["purpose"] == "晚间兜底"
    assert selected["run_at"] == "2026-09-14T21:00:00+08:00"


def test_weekend_evening_fallback_after_review():
    tasks = [{
        "key": "late-final", "sales_day": "2026-09-13",
        "run_at": "2026-09-13T23:00:00+08:00", "hard_lock": "2026-09-13T23:45:00+08:00",
        "status": "scheduled",
    }]
    selected = guard.next_task(datetime.fromisoformat("2026-09-13T13:30:00+08:00"), tasks)
    assert selected["purpose"] == "晚间兜底"
    assert selected["run_at"] == "2026-09-13T22:00:00+08:00"


def test_next_morning_wins_after_evening_fallback():
    selected = guard.next_task(datetime.fromisoformat("2026-09-14T21:10:00+08:00"), [])
    assert selected["purpose"] == "预扫描"
    assert selected["run_at"] == "2026-09-15T10:00:00+08:00"


def test_clear_registry_skips_empty_evening_poll():
    tasks = [{
        "key": "done", "sales_day": "2026-09-30",
        "run_at": "2026-09-30T17:00:00+08:00", "status": "completed",
    }]
    selected = guard.next_task(datetime.fromisoformat("2026-09-30T17:05:00+08:00"), tasks)
    assert selected["purpose"] == "预扫描"
    assert selected["run_at"] == "2026-10-01T10:00:00+08:00"


def test_explicit_daily_stop_skips_remaining_anchors_and_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    data = tmp_path / "artifacts" / "data"
    data.mkdir(parents=True)
    (data / "sporttery_daily_schedule_override_2026-09-21.json").write_text(
        '{"sales_day":"2026-09-21","stop_remaining_tasks":true}', encoding="utf-8"
    )
    task = {
        "key": "same-day-final",
        "sales_day": "2026-09-21",
        "run_at": "2026-09-21T20:00:00+08:00",
        "hard_lock": "2026-09-21T21:00:00+08:00",
        "status": "scheduled",
    }
    selected = guard.next_task(datetime.fromisoformat("2026-09-21T17:30:00+08:00"), [task])
    assert selected["purpose"] == "预扫描"
    assert selected["run_at"] == "2026-09-22T10:00:00+08:00"


def test_registered_batch_beats_evening_safety_net_at_same_time():
    tasks=[{'key':'2026-10-19|00:30-01:00|终版分析','sales_day':'2026-10-19',
            'run_at':'2026-10-19T21:00:00+08:00','hard_lock':'2026-10-19T21:45:00+08:00','status':'pending_schedule'}]
    selected=guard.next_task(datetime.fromisoformat('2026-10-19T13:20:00+08:00'),tasks)
    assert selected['key']==tasks[0]['key']


def test_review_anchor_beats_registered_batch_at_same_time():
    tasks=[{'key':'2026-10-19|early|终版分析','sales_day':'2026-10-19',
            'run_at':'2026-10-19T13:00:00+08:00','hard_lock':'2026-10-19T13:45:00+08:00','status':'pending_schedule'}]
    selected=guard.next_task(datetime.fromisoformat('2026-10-19T12:20:00+08:00'),tasks)
    assert selected['purpose']=='昨日复盘'


def test_lifecycle_update_derives_status_and_next_wake_from_task():
    state={"schema_version":1,"pending_reschedule":False,"status":"active_waiting_20261019_2100_final"}
    task={"key":"2026-10-24|fixed|预扫描","run_at":"2026-10-24T10:00:00+08:00","purpose":"预扫描"}
    updated=guard.lifecycle_update(state,datetime.fromisoformat("2026-10-24T09:00:00+08:00"),task,"final")
    assert updated["status"]=="active_waiting|2026-10-24|fixed|预扫描"
    assert updated["next_task_key"]=="2026-10-24|fixed|预扫描" and updated["next_run_at"]=="2026-10-24T10:00:00+08:00"
    assert updated["last_stage"]=="final" and updated["last_heartbeat_at"]=="2026-10-24T09:00:00+08:00"
    assert updated["last_run_at"]=="2026-10-24T01:00:00+00:00"
    assert updated["pending_reschedule"] is False and updated["schema_version"]==1


def test_record_heartbeat_replaces_residual_block_without_touching_history(tmp_path, monkeypatch):
    monkeypatch.setattr(guard,"ROOT",tmp_path)
    data=tmp_path/"artifacts"/"data";data.mkdir(parents=True)
    state_path=data/"football_automation_controller_state.json"
    state_path.write_text(json.dumps({"status":"active_waiting_20261019_2100_final","last_run_at":"2026-10-17T03:18:58.068976+00:00","last_stage":"review","confirmed_20261017":{"kept":True}}),encoding="utf-8")
    result=guard.record_heartbeat(datetime.fromisoformat("2026-10-24T09:00:00+08:00"),"final",root=tmp_path)
    saved=json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["next_task_key"]==result["next_task_key"]=="2026-10-24|fixed|预扫描"
    assert saved["status"]=="active_waiting|2026-10-24|fixed|预扫描"
    assert saved["last_run_at"]=="2026-10-24T01:00:00+00:00" and saved["last_stage"]=="final"
    assert saved["confirmed_20261017"]=={"kept":True}
    assert not (data/"football_automation_controller_state.json.tmp").exists()
