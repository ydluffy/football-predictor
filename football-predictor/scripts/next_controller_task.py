"""Read-only merge of daily anchors and schedule-driven registered tasks."""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]

LIFECYCLE_FIELDS = (
    "last_run_at",
    "last_heartbeat_at",
    "last_stage",
    "status",
    "next_task_key",
    "next_run_at",
    "next_purpose",
)


def day_stopped(day):
    path = ROOT / f"artifacts/data/sporttery_daily_schedule_override_{day}.json"
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(payload.get("stop_remaining_tasks"))


def next_task(now, tasks):
    now = now.astimezone(TZ)
    candidates = []
    for offset in (0, 1):
        day = (now + timedelta(days=offset)).date()
        if day_stopped(day):
            continue
        evening_hour = 22 if day.weekday() >= 5 else 21
        anchors = [
            (10, 0, "预扫描"),
            (11, 5, "开售确认"),
            (13, 0, "昨日复盘"),
        ]
        # The evening checkpoint is a safety net for an unfinished sales-day
        # task, not a daily polling anchor.  Once the registry is clear, return
        # directly to the next morning pre-scan.
        open_for_day = any(
            str(task.get("sales_day") or "") == str(day)
            and task.get("status") not in {"completed", "archived", "cancelled", "skipped"}
            for task in tasks
        )
        if open_for_day:
            anchors.append((evening_hour, 0, "晚间兜底"))
        for hour, minute, purpose in anchors:
            at = datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)
            if at > now:
                candidates.append(
                    {"key": f"{day}|fixed|{purpose}", "run_at": at.isoformat(), "purpose": purpose}
                )
    for task in tasks:
        if task.get("status") in {"completed", "archived", "cancelled", "skipped"}:
            continue
        sales_day = task.get("sales_day")
        if sales_day and day_stopped(sales_day):
            continue
        at = datetime.fromisoformat(task["run_at"]).astimezone(TZ)
        lock = task.get("hard_lock") or task.get("sales_cutoff")
        if lock and now >= datetime.fromisoformat(lock).astimezone(TZ):
            continue
        if at > now or lock:
            candidates.append({**task, "run_at": max(at, now + timedelta(minutes=1)).isoformat()})
    def priority(task):
        # Fixed morning/review anchors remain first at equal times. An actual
        # registered batch must beat an evening safety net at the same time.
        fixed = "|fixed|" in task["key"]
        tie = (2 if task.get("purpose") == "晚间兜底" else 0) if fixed else 1
        return datetime.fromisoformat(task["run_at"]), tie
    return min(candidates, key=priority)


def due_batches(now, tasks):
    """Current due registry batches, preserving each immutable batch identity."""
    now = now.astimezone(TZ)
    result = []
    for task in tasks:
        if task.get('purpose') != '终版分析' or task.get('status') in {'completed','archived','cancelled','skipped'}:
            continue
        if day_stopped(task.get('sales_day')):
            continue
        lock = task.get('hard_lock') or task.get('sales_cutoff')
        if not lock or not (datetime.fromisoformat(task['run_at']) <= now < datetime.fromisoformat(lock)):
            continue
        result.append(task)
    return sorted(result, key=lambda t:(t['run_at'],t['key']))


def load_tasks(now, root=ROOT):
    tasks = []
    for offset in (-1, 0, 1):
        day = (now + timedelta(days=offset)).date()
        path = root / f"artifacts/data/sporttery_task_registry_{day}.json"
        if path.exists():
            tasks.extend(json.loads(path.read_text(encoding="utf-8-sig"))["tasks"])
    return tasks


def lifecycle_update(state, now, task, stage):
    """Single writer for the lifecycle block.

    ``status`` and ``next_task_key`` are derived from the selected next task, so a
    stale as-of day can no longer sit next to a fresh heartbeat.
    """
    return {
        **state,
        "last_run_at": now.astimezone(timezone.utc).isoformat(),
        "last_heartbeat_at": now.astimezone(TZ).isoformat(),
        "last_stage": stage,
        "status": f"active_waiting|{task['key']}",
        "next_task_key": task["key"],
        "next_run_at": task["run_at"],
        "next_purpose": task.get("purpose"),
    }


def record_heartbeat(now, stage, root=ROOT):
    state_path = root / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8-sig"))
    updated = lifecycle_update(state, now, next_task(now, load_tasks(now, root)), stage)
    temporary = state_path.with_name(state_path.name + ".tmp")
    temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(state_path)
    return {field: updated[field] for field in LIFECYCLE_FIELDS}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of")
    parser.add_argument("--due-batches", action="store_true")
    parser.add_argument("--record-heartbeat", action="store_true")
    parser.add_argument("--stage")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.as_of) if args.as_of else datetime.now(TZ)
    if args.record_heartbeat:
        if not args.stage:
            parser.error("--stage is required with --record-heartbeat")
        print(json.dumps(record_heartbeat(now, args.stage), ensure_ascii=False, indent=2))
        return
    tasks = load_tasks(now)
    print(json.dumps(due_batches(now, tasks) if args.due_batches else next_task(now, tasks), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
