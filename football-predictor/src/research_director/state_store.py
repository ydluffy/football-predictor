from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import ensure_project_dirs, get_settings


@dataclass(frozen=True)
class StoredStep:
    run_id: str
    step_id: str
    step_key: str | None
    agent: str
    workflow: str
    status: str
    attempt: int | None
    started_at: str | None
    finished_at: str | None
    summary: str
    error_json: str | None


class ResearchStateStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        ensure_project_dirs()
        s = get_settings()
        self._db_path = Path(db_path) if db_path is not None else s.research_director_state_db_path
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
                  workflow TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  status TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS steps(
                  step_id TEXT PRIMARY KEY,
                  run_id TEXT NOT NULL,
                  step_key TEXT,
                  agent TEXT NOT NULL,
                  workflow TEXT NOT NULL,
                  status TEXT NOT NULL,
                  attempt INTEGER,
                  params_json TEXT NOT NULL,
                  error_json TEXT,
                  started_at TEXT,
                  finished_at TEXT,
                  summary TEXT NOT NULL,
                  FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts(
                  artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  step_id TEXT NOT NULL,
                  name TEXT NOT NULL,
                  path TEXT NOT NULL,
                  artifact_type TEXT NOT NULL,
                  sha256 TEXT,
                  created_at TEXT NOT NULL,
                  metadata_json TEXT NOT NULL,
                  FOREIGN KEY(step_id) REFERENCES steps(step_id) ON DELETE CASCADE
                );
                """
            )
            self._ensure_step_columns(conn)

    def _ensure_step_columns(self, conn: sqlite3.Connection) -> None:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(steps)").fetchall()]
        if "step_key" not in cols:
            conn.execute("ALTER TABLE steps ADD COLUMN step_key TEXT;")
        if "attempt" not in cols:
            conn.execute("ALTER TABLE steps ADD COLUMN attempt INTEGER;")
        if "error_json" not in cols:
            conn.execute("ALTER TABLE steps ADD COLUMN error_json TEXT;")

    def create_run(self, *, run_id: str, workflow: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO runs(run_id, workflow, created_at, status) VALUES(?,?,?,?)",
                (str(run_id), str(workflow), now, "planned"),
            )

    def set_run_status(self, *, run_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE runs SET status=? WHERE run_id=?", (str(status), str(run_id)))

    def add_step(self, *, run_id: str, step_id: str, agent: str, workflow: str, status: str, params: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO steps(step_id, run_id, step_key, agent, workflow, status, attempt, params_json, error_json, started_at, finished_at, summary) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (step_id, run_id, str(params.get("step_key") or ""), agent, workflow, status, int(params.get("attempt") or 1), json.dumps(self._jsonable(params), ensure_ascii=False), None, None, None, ""),
            )

    def update_step(
        self,
        *,
        step_id: str,
        status: str,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        summary: str | None = None,
        error: dict[str, Any] | None = None,
        attempt: int | None = None,
    ) -> None:
        started = started_at.astimezone(timezone.utc).isoformat() if started_at else None
        finished = finished_at.astimezone(timezone.utc).isoformat() if finished_at else None
        error_json = json.dumps(self._jsonable(error or {}), ensure_ascii=False) if error is not None else None
        with self._connect() as conn:
            if summary is None and error is None and attempt is None:
                conn.execute(
                    "UPDATE steps SET status=?, started_at=COALESCE(?, started_at), finished_at=COALESCE(?, finished_at) WHERE step_id=?",
                    (str(status), started, finished, str(step_id)),
                )
                return

            sets = ["status=?"]
            args: list[Any] = [str(status)]
            sets.append("started_at=COALESCE(?, started_at)")
            args.append(started)
            sets.append("finished_at=COALESCE(?, finished_at)")
            args.append(finished)
            if summary is not None:
                sets.append("summary=?")
                args.append(str(summary))
            if error is not None:
                sets.append("error_json=?")
                args.append(error_json)
            if attempt is not None:
                sets.append("attempt=?")
                args.append(int(attempt))
            args.append(str(step_id))
            conn.execute(f"UPDATE steps SET {', '.join(sets)} WHERE step_id=?", tuple(args))

    def add_artifact(
        self,
        *,
        step_id: str,
        name: str,
        path: str,
        artifact_type: str,
        sha256: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO artifacts(step_id, name, path, artifact_type, sha256, created_at, metadata_json) VALUES(?,?,?,?,?,?,?)",
                (str(step_id), str(name), str(path), str(artifact_type), sha256, now, json.dumps(metadata or {}, ensure_ascii=False)),
            )

    def list_steps(self, *, run_id: str) -> list[StoredStep]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT run_id, step_id, step_key, agent, workflow, status, attempt, started_at, finished_at, summary, error_json FROM steps WHERE run_id=? ORDER BY step_id",
                (str(run_id),),
            ).fetchall()
        return [
            StoredStep(
                run_id=r[0],
                step_id=r[1],
                step_key=r[2],
                agent=r[3],
                workflow=r[4],
                status=r[5],
                attempt=r[6],
                started_at=r[7],
                finished_at=r[8],
                summary=r[9],
                error_json=r[10],
            )
            for r in rows
        ]

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
        except Exception:
            pass
        return {"__type__": type(value).__name__, "repr": str(value)[:200]}
