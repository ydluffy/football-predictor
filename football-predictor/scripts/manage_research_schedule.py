"""Manual controls and an allowlisted data-quality worker (no betting execution)."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research_director.manual_schedule import TZ, ScheduleStore  # noqa: E402

BASE = ROOT / "artifacts" / "research_schedule"


def seed(store, now):
    for offset in (0, 1):
        day = (now + timedelta(days=offset)).date()
        for kind in ("intelligence_validation", "coverage_audit"):
            at = datetime(day.year, day.month, day.day, 11, 0, tzinfo=TZ)
            store.plan(f"{day}:{kind}", kind, at, now, update_default=True)


def execute(task):
    # Task data never supplies a program, arguments, or an output path.
    key = hashlib.sha256(task["id"].encode()).hexdigest()[:20]
    output = BASE / "runs" / f'{key}-{task["attempt"]}'
    output.mkdir(parents=True, exist_ok=False)
    if task["kind"] == "intelligence_validation":
        args = ["scripts/validate_prematch_intelligence.py",
                "--output", str(output / "validated.csv"),
                "--audit-output", str(output / "audit.json"), "--fail-on-rejected"]
    elif task["kind"] == "coverage_audit":
        args = ["scripts/audit_prematch_intelligence_coverage.py",
                "--json-output", str(output / "audit.json"),
                "--markdown-output", str(output / "report.md")]
    else:
        raise ValueError("任务类型未获执行许可")
    with (output / "execution.log").open("w", encoding="utf-8") as log:
        completed = subprocess.run([sys.executable, *args], cwd=ROOT, stdout=log,
                                   stderr=subprocess.STDOUT, timeout=600, check=False)
    if completed.returncode:
        raise RuntimeError(f"校验/审计未通过，exit={completed.returncode}，证据：{output}")
    return {"artifact_directory": str(output), "returncode": completed.returncode}


def tick(store, event_id=None):
    now = datetime.now(TZ)
    task_ids = None
    if event_id:
        digest = hashlib.sha256(event_id.encode()).hexdigest()
        task_ids = {f"collection:{digest}:{kind}"
                    for kind in ("intelligence_validation", "coverage_audit")}
        for task_id in task_ids:
            store.plan(task_id, task_id.rsplit(":", 1)[1], now, now)
    else:
        seed(store, now)
    completed = []
    for _ in range(4):
        task = store.claim(datetime.now(TZ), task_ids=task_ids)
        if task is None:
            break
        result, error = None, None
        try:
            result = execute(task)
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            error = str(exc)
        completed.append(store.finish(task["id"], task["revision"], datetime.now(TZ),
                                      result=result, error=error))
    snapshot = store.inspect(datetime.now(TZ))
    return {"executed": completed, "next_due_at": snapshot["next_due_at"],
            "failed_tasks": [t["id"] for t in snapshot["tasks"] if t["status"] == "failed"],
            "event_tasks": [t for t in snapshot["tasks"] if task_ids and t["id"] in task_ids],
            "scope": "local_data_quality_only"}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "inspect", "tick", "after-collection", "reschedule", "pause",
                                          "resume", "cancel", "run_once", "revert"])
    parser.add_argument("--task-id")
    parser.add_argument("--command-id")
    parser.add_argument("--revision", type=int)
    parser.add_argument("--at", help="ISO8601 with timezone")
    parser.add_argument("--until", help="ISO8601 with timezone")
    parser.add_argument("--reference", help="Command ID to revert")
    parser.add_argument("--event-id", help="Stable successful collection batch identifier")
    args = parser.parse_args()
    store = ScheduleStore(BASE / "schedule.sqlite3")
    now = datetime.now(TZ)
    if args.action == "plan":
        seed(store, now)
        result = store.inspect(now)
    elif args.action == "inspect":
        result = store.inspect(now)
    elif args.action == "tick":
        result = tick(store)
    elif args.action == "after-collection":
        if not args.event_id:
            parser.error("采集后审计需要稳定的 --event-id")
        result = tick(store, event_id=args.event_id)
    else:
        if not args.task_id or not args.command_id or args.revision is None:
            parser.error("人工命令必须提供 --task-id、--command-id、--revision")
        result = store.command(args.command_id, args.task_id, args.action, args.revision,
                               now, at=args.at, until=args.until, reference=args.reference)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
