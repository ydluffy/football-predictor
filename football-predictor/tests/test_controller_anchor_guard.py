import importlib.util
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
    assert (
        guard.next_task(datetime.fromisoformat("2026-09-04T15:00:00+08:00"), tasks)["purpose"]
        == "预扫描"
    )
