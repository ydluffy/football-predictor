"""Read-only merge of daily anchors and schedule-driven registered tasks."""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]


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
    return min(candidates, key=lambda t: datetime.fromisoformat(t["run_at"]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.as_of) if args.as_of else datetime.now(TZ)
    tasks = []
    for offset in (-1, 0, 1):
        day = (now + timedelta(days=offset)).date()
        path = ROOT / f"artifacts/data/sporttery_task_registry_{day}.json"
        if path.exists():
            tasks.extend(json.loads(path.read_text(encoding="utf-8-sig"))["tasks"])
    print(json.dumps(next_task(now, tasks), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
