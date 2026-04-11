from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


def get_db_path() -> Path:
    env = os.getenv("P0_DB_PATH")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data" / "p0.sqlite3"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fixtures (
            fixture_id INTEGER PRIMARY KEY,
            competition_code TEXT,
            competition_name TEXT,
            season INTEGER,
            matchday INTEGER,
            utc_date TEXT,
            status TEXT,
            home_team_id INTEGER,
            home_team_name TEXT,
            away_team_id INTEGER,
            away_team_name TEXT,
            home_score INTEGER,
            away_score INTEGER,
            last_updated TEXT
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fixtures_utc_date ON fixtures(utc_date)")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_fixtures_team_date ON fixtures(home_team_id, away_team_id, utc_date)"
    )
    conn.commit()


def upsert_fixtures(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    init_db(conn)
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    values: list[tuple[Any, ...]] = []
    for r in rows:
        values.append(
            (
                int(r["fixture_id"]),
                r.get("competition_code"),
                r.get("competition_name"),
                r.get("season"),
                r.get("matchday"),
                r.get("utc_date"),
                r.get("status"),
                r.get("home_team_id"),
                r.get("home_team_name"),
                r.get("away_team_id"),
                r.get("away_team_name"),
                r.get("home_score"),
                r.get("away_score"),
                now,
            )
        )
    conn.executemany(
        """
        INSERT INTO fixtures (
            fixture_id, competition_code, competition_name, season, matchday, utc_date, status,
            home_team_id, home_team_name, away_team_id, away_team_name, home_score, away_score, last_updated
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fixture_id) DO UPDATE SET
            competition_code=excluded.competition_code,
            competition_name=excluded.competition_name,
            season=excluded.season,
            matchday=excluded.matchday,
            utc_date=excluded.utc_date,
            status=excluded.status,
            home_team_id=excluded.home_team_id,
            home_team_name=excluded.home_team_name,
            away_team_id=excluded.away_team_id,
            away_team_name=excluded.away_team_name,
            home_score=excluded.home_score,
            away_score=excluded.away_score,
            last_updated=excluded.last_updated
        """,
        values,
    )
    conn.commit()
    return len(values)


def select_fixtures_by_date(conn: sqlite3.Connection, date_from: str, date_to: str) -> list[dict[str, Any]]:
    init_db(conn)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM fixtures
        WHERE substr(utc_date, 1, 10) >= ? AND substr(utc_date, 1, 10) <= ?
        ORDER BY utc_date ASC
        """,
        (date_from, date_to),
    )
    return [dict(r) for r in cur.fetchall()]


def get_fixture(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    init_db(conn)
    cur = conn.cursor()
    cur.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fixture_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def select_recent_finished_matches(
    conn: sqlite3.Connection,
    team_id: int,
    before_utc: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    init_db(conn)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM fixtures
        WHERE status='FINISHED'
          AND utc_date < ?
          AND (home_team_id=? OR away_team_id=?)
          AND home_score IS NOT NULL AND away_score IS NOT NULL
        ORDER BY utc_date DESC
        LIMIT ?
        """,
        (before_utc, team_id, team_id, limit),
    )
    return [dict(r) for r in cur.fetchall()]

