from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import ensure_project_dirs, get_settings
from multi_agent.schemas import TaskOutcome, TaskSpec, TaskStatus, WorkflowKind


@dataclass(frozen=True)
class StoredRun:
    run_id: str
    kind: str
    created_at: str
    status: str


class SQLiteStateStore:
    def _jsonable(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(k): self._jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._jsonable(v) for v in value]

        try:
            import pandas as pd  # type: ignore

            if isinstance(value, pd.DataFrame):
                return {"__type__": "DataFrame", "shape": [int(value.shape[0]), int(value.shape[1])], "columns": [str(c) for c in value.columns[:50]]}
            if isinstance(value, pd.Series):
                return {"__type__": "Series", "length": int(value.shape[0]), "name": str(value.name)}
        except Exception:
            pass

        return {"__type__": type(value).__name__, "repr": str(value)[:200]}

    def __init__(self, db_path: str | Path | None = None) -> None:
        ensure_project_dirs()
        s = get_settings()
        self._db_path = Path(db_path) if db_path is not None else s.agent_state_db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs(
                  run_id TEXT PRIMARY KEY,
                  kind TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  status TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks(
                  task_id TEXT PRIMARY KEY,
                  run_id TEXT NOT NULL,
                  agent TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  risk_level TEXT NOT NULL,
                  status TEXT NOT NULL,
                  params_json TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts(
                  artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  task_id TEXT NOT NULL,
                  name TEXT NOT NULL,
                  path TEXT NOT NULL,
                  artifact_type TEXT NOT NULL,
                  sha256 TEXT,
                  created_at TEXT NOT NULL,
                  metadata_json TEXT NOT NULL,
                  FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                );
                """
            )

    def create_run(self, *, run_id: str, kind: WorkflowKind) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs(run_id, kind, created_at, status) VALUES(?,?,?,?)",
                (str(run_id), str(kind.value), now, TaskStatus.planned.value),
            )

    def add_task(self, *, run_id: str, task: TaskSpec) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO tasks(task_id, run_id, agent, kind, risk_level, status, params_json, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    task.task_id,
                    run_id,
                    task.agent.value,
                    task.kind.value,
                    task.risk_level.value,
                    TaskStatus.planned.value,
                    json.dumps(self._jsonable(task.params), ensure_ascii=False),
                    now,
                ),
            )

    def set_task_status(self, *, task_id: str, status: TaskStatus) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE tasks SET status=? WHERE task_id=?", (status.value, task_id))

    def add_artifact(self, *, task_id: str, name: str, path: str, artifact_type: str, sha256: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO artifacts(task_id, name, path, artifact_type, sha256, created_at, metadata_json) VALUES(?,?,?,?,?,?,?)",
                (
                    task_id,
                    str(name),
                    str(path),
                    str(artifact_type),
                    sha256,
                    now,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )

    def get_task_status(self, task_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT status FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return row[0] if row else None

    def list_runs(self) -> list[StoredRun]:
        with self._connect() as conn:
            rows = conn.execute("SELECT run_id, kind, created_at, status FROM runs ORDER BY created_at DESC").fetchall()
        return [StoredRun(run_id=r[0], kind=r[1], created_at=r[2], status=r[3]) for r in rows]

    def record_outcome(self, outcome: TaskOutcome) -> None:
        self.set_task_status(task_id=outcome.task_id, status=outcome.status)
        for a in outcome.artifacts:
            self.add_artifact(
                task_id=outcome.task_id,
                name=a.name,
                path=a.path,
                artifact_type=a.artifact_type,
                sha256=a.sha256,
                metadata=a.metadata,
            )
