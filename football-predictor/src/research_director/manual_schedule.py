"""Transactional scheduler for allowlisted data-quality work, not production plans."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))
KINDS = frozenset({"coverage_audit", "intelligence_validation"})


def timestamp(value: str | datetime) -> str:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        raise ValueError("时间必须带时区，例如 +08:00")
    return parsed.astimezone(TZ).isoformat(timespec="seconds")


def encode(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class ScheduleStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.transaction() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, body TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commands (
                    id TEXT PRIMARY KEY, request TEXT NOT NULL, receipt TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, task_id TEXT NOT NULL, body TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS plan_changes (
                    seq INTEGER PRIMARY KEY, body TEXT NOT NULL
                );
            """)

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _get(conn, task_id):
        row = conn.execute("SELECT body FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise ValueError(f"未知任务: {task_id}")
        return json.loads(row[0])

    @staticmethod
    def _put(conn, task):
        conn.execute("INSERT OR REPLACE INTO tasks VALUES (?, ?)",
                     (task["id"], encode(task)))

    def plan(self, task_id, kind, run_at, now, *, update_default=False):
        if kind not in KINDS:
            raise ValueError("该任务类型未通过数据质量执行白名单")
        run_at, now = timestamp(run_at), timestamp(now)
        with self.transaction() as conn:
            row = conn.execute("SELECT body FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row:
                task = json.loads(row[0])
                if task["kind"] != kind:
                    raise ValueError("稳定任务 ID 不允许改变任务类型")
                if (update_default and task["status"] == "pending" and not task["manual"]
                        and task["run_at"] != run_at):
                    before = dict(task)
                    task.update(run_at=run_at, planned_at=run_at, updated_at=now,
                                revision=task["revision"] + 1)
                    self._put(conn, task)
                    conn.execute("INSERT INTO plan_changes(body) VALUES (?)",
                                 (encode({"before": before, "after": task, "at": now}),))
                return task
            task = dict(id=task_id, kind=kind, planned_at=run_at, run_at=run_at,
                        status="pending", revision=1, attempt=0, pause_until=None,
                        created_at=now, updated_at=now, manual=False)
            self._put(conn, task)
            return task

    def inspect(self, now):
        now = timestamp(now)
        with self.transaction() as conn:
            tasks = [json.loads(r[0]) for r in conn.execute("SELECT body FROM tasks")]
            runs = [json.loads(r[0]) for r in conn.execute("SELECT body FROM runs")]
        for task in tasks:
            task["effective_status"] = self._effective(task, now)
        eligible = [max(t["run_at"], now) for t in tasks
                    if t["effective_status"] == "pending"]
        eligible.extend(max(t["run_at"], t["pause_until"], now) for t in tasks
                        if t["effective_status"] == "paused" and t.get("pause_until"))
        next_at = min(eligible, default=None)
        return {"as_of": now, "tasks": sorted(tasks, key=lambda t: (t["run_at"], t["id"])),
                "next_due_at": next_at, "runs": runs,
                "platform_status": "separate_platform_receipt_required"}

    @staticmethod
    def _effective(task, now):
        if (task["status"] == "paused" and task.get("pause_until")
                and now >= task["pause_until"]):
            return "pending"
        return task["status"]

    def command(self, command_id, task_id, action, revision, now, at=None, until=None,
                reference=None):
        if not command_id.strip():
            raise ValueError("command_id 不能为空")
        request = dict(task_id=task_id, action=action, revision=revision,
                       at=timestamp(at) if at else None,
                       until=timestamp(until) if until else None, reference=reference)
        now = timestamp(now)
        with self.transaction() as conn:
            previous = conn.execute("SELECT request,receipt FROM commands WHERE id=?",
                                    (command_id,)).fetchone()
            if previous:
                if previous[0] != encode(request):
                    raise ValueError("同一命令 ID 不能用于不同请求")
                return json.loads(previous[1])
            task = self._get(conn, task_id)
            before = dict(task)
            if task["revision"] != revision:
                raise ValueError("版本冲突，请重新读取计划")
            if task["status"] == "running":
                raise ValueError("任务正在执行；请等待结束后调整，不能撤销已发生的写入")
            self._apply(conn, task, request, now)
            task.update(revision=revision + 1, updated_at=now, manual=True)
            self._put(conn, task)
            receipt = dict(command_id=command_id, status="committed_local",
                           before=before, after=task, received_at=now,
                           platform_status="polling_worker_required")
            conn.execute("INSERT INTO commands VALUES (?,?,?)",
                         (command_id, encode(request), encode(receipt)))
            return receipt

    @staticmethod
    def _revert(conn, task, reference):
        row = conn.execute("SELECT receipt FROM commands WHERE id=?", (reference,)).fetchone()
        receipt = json.loads(row[0]) if row else None
        if (not receipt or receipt["after"]["id"] != task["id"]
                or receipt["after"]["revision"] != task["revision"]):
            raise ValueError("只能撤销该任务最新且尚未执行的命令")
        task.update(receipt["before"])

    def _apply(self, conn, task, request, now):
        action = request["action"]
        if action == "revert":
            self._revert(conn, task, request["reference"])
            return
        if action == "run_once":
            if task["status"] != "failed":
                raise ValueError("补跑只接受失败任务；完成任务不会自动重跑")
            task.update(status="pending", run_at=now, pause_until=None)
            return
        if task["status"] not in {"pending", "paused"}:
            raise ValueError("终态任务不可改期或恢复；失败任务请使用补跑")
        self._edit_pending(task, request, now)

    @staticmethod
    def _edit_pending(task, request, now):
        action = request["action"]
        if action == "reschedule":
            if not request["at"] or request["at"] <= now:
                raise ValueError("改期必须指定未来的带时区时间")
            task["run_at"] = request["at"]
        elif action == "pause":
            if request["until"] and request["until"] <= now:
                raise ValueError("暂停截止时间必须在未来")
            task.update(status="paused", pause_until=request["until"])
        elif action == "resume":
            if task["status"] != "paused":
                raise ValueError("任务未暂停")
            task.update(status="pending", pause_until=None)
        elif action == "cancel":
            task.update(status="cancelled", pause_until=None)
        else:
            raise ValueError("未知命令")

    def claim(self, now, task_ids=None):
        now = timestamp(now)
        with self.transaction() as conn:
            tasks = [json.loads(r[0]) for r in conn.execute("SELECT body FROM tasks")]
            # No automatic replay after a process crash: output may already exist.
            for task in tasks:
                if task["status"] == "running" and task["lease_until"] <= now:
                    task.update(status="failed", error="worker_lease_expired_review_before_retry",
                                revision=task["revision"] + 1, updated_at=now)
                    self._put(conn, task)
                    self._finish_run(conn, task, now)
            due = [t for t in tasks if self._effective(t, now) == "pending"
                   and t["run_at"] <= now and (task_ids is None or t["id"] in task_ids)]
            if not due:
                return None
            task = min(due, key=lambda t: (t["run_at"], t["id"]))
            if task["kind"] not in KINDS:
                raise ValueError("数据库任务类型不在执行白名单内")
            task.update(status="running", attempt=task["attempt"] + 1,
                        revision=task["revision"] + 1, started_at=now, updated_at=now,
                        lease_until=timestamp(datetime.fromisoformat(now) + timedelta(minutes=15)))
            self._put(conn, task)
            self._finish_run(conn, task, now)
            return task

    @staticmethod
    def _finish_run(conn, task, now):
        run_id = f'{task["id"]}#{task["attempt"]}'
        conn.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?)",
                     (run_id, task["id"], encode({**task, "recorded_at": now})))

    def finish(self, task_id, revision, now, result=None, error=None):
        now = timestamp(now)
        with self.transaction() as conn:
            task = self._get(conn, task_id)
            if (task["status"] != "running" or task["revision"] != revision
                    or now >= task["lease_until"]):
                raise ValueError("执行租约已失效，不能覆盖新状态")
            task.update(status="failed" if error else "succeeded", result=result,
                        error=error, completed_at=now, updated_at=now,
                        revision=revision + 1)
            self._put(conn, task)
            self._finish_run(conn, task, now)
            return task
