"""Read-only merge of mandatory daily anchors and unfinished registered tasks."""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]


def next_task(now, tasks):
    now = now.astimezone(TZ)
    candidates = []
    for offset in (0, 1):
        day = (now + timedelta(days=offset)).date()
        for hour, minute, purpose in ((10, 0, "预扫描"), (11, 5, "开售确认"), (13, 0, "昨日复盘")):
            at = datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)
            if at > now:
                candidates.append(
                    {"key": f"{day}|fixed|{purpose}", "run_at": at.isoformat(), "purpose": purpose}
                )
    for task in tasks:
        if task.get("status") == "completed":
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
