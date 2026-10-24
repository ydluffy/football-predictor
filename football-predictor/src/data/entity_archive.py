"""Local, source-scoped football identities and immutable observations."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5


def packed(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def identity(kind, provider_id):
    if provider_id is None or isinstance(provider_id, bool) or not str(provider_id).isdigit():
        raise ValueError("missing or invalid provider identity")
    return str(uuid5(NAMESPACE_URL, f"api_football:{kind}:{provider_id}"))


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, provider TEXT NOT NULL,
            provider_id TEXT NOT NULL, name TEXT NOT NULL,
            UNIQUE(kind, provider, provider_id));
        CREATE TABLE IF NOT EXISTS observations (
            id TEXT PRIMARY KEY, entity_id TEXT NOT NULL REFERENCES entities(id),
            kind TEXT NOT NULL, observed_at TEXT NOT NULL, evidence TEXT NOT NULL,
            sha256 TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reviews (
            id TEXT PRIMARY KEY, entity_id TEXT NOT NULL REFERENCES entities(id),
            reason TEXT NOT NULL, detail TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', reviewer TEXT, note TEXT,
            reviewed_at TEXT);
    """)
    return db


def review(db, entity_id, reason, detail):
    material = packed([entity_id, reason, detail])
    db.execute("INSERT OR IGNORE INTO reviews(id,entity_id,reason,detail) VALUES(?,?,?,?)",
               (hashlib.sha256(material.encode()).hexdigest(), entity_id, reason, packed(detail)))


def entity(db, kind, item):
    eid = identity(kind, item.get("id"))
    name = str(item.get("name") or "").strip()
    if not name:
        raise ValueError("entity name missing")
    old = db.execute("SELECT name FROM entities WHERE id=?", (eid,)).fetchone()
    if old is None:
        db.execute("INSERT INTO entities VALUES(?,?,?,?,?)", (eid, kind, "api_football", str(item["id"]), name))
        review(db, eid, "new_identity", {"name": name, "provider_id": item["id"]})
    elif old[0] != name:
        review(db, eid, "name_conflict", {"stored": old[0], "incoming": name})
    return eid


def observe(db, eid, kind, payload, evidence):
    material = packed([eid, kind, payload, evidence])
    db.execute("INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?,?)", (
        hashlib.sha256(material.encode()).hexdigest(), eid, kind,
        evidence["observed_at"], evidence["path"], evidence["sha256"], packed(payload)))


def ingest(db, audit, fixture_ids):
    """Import only selected fixtures, atomically; missing data never clears history."""
    observed = datetime.fromisoformat(audit["observed_at"])
    if observed.tzinfo is None:
        raise ValueError("observation time requires timezone")
    fixture_ids = {str(x) for x in fixture_ids}
    files = []
    for value in audit["raw_files"]:
        path = Path(value)
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if digest[:12] != path.stem.rsplit("_", 1)[1]:
            raise ValueError("archive digest mismatch")
        payload = json.loads(content)
        if payload.get("errors"):
            continue
        files.append((path, payload.get("response") or [], {
            "path": str(path.resolve()), "sha256": digest, "observed_at": observed.isoformat()}))
    with db:
        # Fixtures establish team/competition references before player observations.
        for path, rows, evidence in files:
            if "_fixtures_" not in path.name and "_calendar_" not in path.name:
                continue
            for row in rows:
                fixture = row["fixture"]
                if str(fixture["id"]) not in fixture_ids:
                    continue
                teams = {side: entity(db, "team", row["teams"][side]) for side in ("home", "away")}
                league = entity(db, "competition", row["league"])
                for side, eid in teams.items():
                    observe(db, eid, "team_profile", {"name": row["teams"][side]["name"],
                        "gender": None, "age_group": None, "reserve": None}, evidence)
                observe(db, league, "season", {"season": row["league"].get("season"),
                    "country": row["league"].get("country"), "team_ids": sorted(teams.values())}, evidence)
                fid = entity(db, "fixture", {"id": fixture["id"], "name": str(fixture["id"])})
                state = {"home_id": teams["home"], "away_id": teams["away"], "competition_id": league,
                         "season": row["league"].get("season"), "kickoff": fixture["date"],
                         "status": fixture.get("status")}
                previous = db.execute("SELECT payload FROM observations WHERE entity_id=? AND kind='fixture'", (fid,)).fetchall()
                for (value,) in previous:
                    old = json.loads(value)
                    fields = ("home_id", "away_id", "competition_id", "season", "kickoff")
                    if any(old.get(k) != state.get(k) for k in fields):
                        review(db, fid, "fixture_changed", {"previous": old, "incoming": state})
                observe(db, fid, "fixture", state, evidence)
        for path, rows, evidence in files:
            if "_injuries_" in path.name:
                for row in rows:
                    if str(row["fixture"]["id"]) in fixture_ids:
                        player_observation(db, row["player"], row["team"], row["fixture"]["id"],
                                           "absence", {"type": row["player"].get("type"),
                                                       "reason": row["player"].get("reason")}, evidence)
            elif "_lineups_" in path.name:
                source_id = path.stem.split("_lineups_", 1)[1].rsplit("_", 1)[0]
                if source_id not in fixture_ids:
                    continue
                for row in rows:
                    for field, role in (("startXI", "starter"), ("substitutes", "substitute")):
                        for entry in row.get(field) or []:
                            player_observation(db, entry["player"], row["team"], source_id,
                                               "lineup", {"role": role, "position": entry["player"].get("pos")}, evidence)


def player_observation(db, player, team, source_fixture, kind, details, evidence):
    fid = identity("fixture", source_fixture)
    if db.execute("SELECT 1 FROM entities WHERE id=?", (fid,)).fetchone() is None:
        raise ValueError("player observation has no archived fixture")
    pid = entity(db, "player", player)
    tid = entity(db, "team", team)
    observe(db, pid, "membership_observation", {"team_id": tid, "fixture_id": fid,
        "valid_from": None, "valid_to": None, "basis": kind}, evidence)
    observe(db, pid, kind, {**details, "team_id": tid, "fixture_id": fid}, evidence)


def report(db):
    return {"entities": dict(db.execute("SELECT kind,count(*) FROM entities GROUP BY kind")),
            "observations": dict(db.execute("SELECT kind,count(*) FROM observations GROUP BY kind")),
            "reviews": dict(db.execute("SELECT status,count(*) FROM reviews GROUP BY status"))}
