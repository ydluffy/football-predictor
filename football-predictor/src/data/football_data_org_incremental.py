from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd


COMPETITIONS = {
    "PL": {"competition_id": "ENG_PREMIER_LEAGUE", "division": "E0"},
    "PD": {"competition_id": "ESP_LA_LIGA", "division": "SP1"},
    "BL1": {"competition_id": "GER_BUNDESLIGA", "division": "D1"},
    "FL1": {"competition_id": "FRA_LIGUE_1", "division": "F1"},
    "SA": {"competition_id": "ITA_SERIE_A", "division": "I1"},
    "DED": {"competition_id": "NED_EREDIVISIE", "division": "N1"},
    "PPL": {"competition_id": "POR_PRIMEIRA_LIGA", "division": "P1"},
}
MATCH_COLUMNS = [
    "record_id", "snapshot_id", "captured_at", "source_match_id", "competition_code",
    "competition_id", "league", "season", "matchday", "kickoff_at", "status", "stage",
    "home_team_id", "home_team", "away_team_id", "away_team", "half_home_score",
    "half_away_score", "home_score", "away_score", "winner", "last_updated", "source",
]
STANDING_COLUMNS = [
    "record_id", "snapshot_id", "captured_at", "competition_code", "competition_id",
    "season", "stage", "standing_type", "position", "team_id", "team", "played_games",
    "won", "draw", "lost", "points", "goals_for", "goals_against", "goal_difference", "source",
]
TEAM_COLUMNS = [
    "record_id", "snapshot_id", "captured_at", "competition_code", "competition_id",
    "team_id", "team", "short_name", "tla", "coach_id", "coach_name", "venue", "source",
]
SQUAD_COLUMNS = [
    "record_id", "snapshot_id", "captured_at", "competition_code", "competition_id",
    "team_id", "team", "player_id", "player", "position", "date_of_birth", "nationality", "source",
]
V2_RESULT_COLUMNS = [
    "source_match_id", "date", "kickoff_at", "competition_code", "competition_id",
    "league", "season", "matchday", "home_team", "away_team", "home_goals",
    "away_goals", "actual_result", "captured_at", "source",
]


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _record_id(*parts: object) -> str:
    return _digest("|".join(str(part) for part in parts).encode("utf-8"))[:24]


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        raise ValueError("captured_at must be timezone-aware")
    return parsed


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise RuntimeError(f"immutable archive collision: {path}")
        return
    part = path.with_suffix(path.suffix + ".part")
    part.write_bytes(content)
    part.replace(path)


def normalize_matches(payload: dict[str, Any], *, snapshot_id: str, captured_at: object) -> pd.DataFrame:
    captured = _timestamp(captured_at).isoformat()
    rows: list[dict[str, Any]] = []
    for item in payload.get("matches") or []:
        competition = item.get("competition") or {}
        code = str(competition.get("code") or "")
        meta = COMPETITIONS.get(code, {"competition_id": code, "division": code})
        season = item.get("season") or {}
        home = item.get("homeTeam") or {}
        away = item.get("awayTeam") or {}
        score = item.get("score") or {}
        full = score.get("fullTime") or {}
        half = score.get("halfTime") or {}
        match_id = str(item.get("id") or "")
        if not match_id:
            continue
        rows.append({
            "record_id": _record_id(snapshot_id, match_id), "snapshot_id": snapshot_id,
            "captured_at": captured, "source_match_id": match_id, "competition_code": code,
            "competition_id": meta["competition_id"], "league": meta["division"],
            "season": str(season.get("startDate") or "")[:4], "matchday": item.get("matchday", ""),
            "kickoff_at": item.get("utcDate", ""), "status": item.get("status", ""),
            "stage": item.get("stage", ""), "home_team_id": str(home.get("id") or ""),
            "home_team": home.get("name") or home.get("shortName") or "",
            "away_team_id": str(away.get("id") or ""),
            "away_team": away.get("name") or away.get("shortName") or "",
            "half_home_score": half.get("home", ""), "half_away_score": half.get("away", ""),
            "home_score": full.get("home", ""), "away_score": full.get("away", ""),
            "winner": score.get("winner", ""), "last_updated": item.get("lastUpdated", ""),
            "source": "football_data_org",
        })
    return pd.DataFrame(rows, columns=MATCH_COLUMNS)


def normalize_standings(payload: dict[str, Any], *, code: str, snapshot_id: str, captured_at: object) -> pd.DataFrame:
    captured = _timestamp(captured_at).isoformat()
    meta = COMPETITIONS[code]
    season = str((payload.get("season") or {}).get("startDate") or "")[:4]
    rows: list[dict[str, Any]] = []
    for standing in payload.get("standings") or []:
        for item in standing.get("table") or []:
            team = item.get("team") or {}
            team_id = str(team.get("id") or "")
            rows.append({
                "record_id": _record_id(snapshot_id, code, standing.get("type"), team_id),
                "snapshot_id": snapshot_id, "captured_at": captured, "competition_code": code,
                "competition_id": meta["competition_id"], "season": season,
                "stage": standing.get("stage", ""), "standing_type": standing.get("type", ""),
                "position": item.get("position", ""), "team_id": team_id,
                "team": team.get("name", ""), "played_games": item.get("playedGames", ""),
                "won": item.get("won", ""), "draw": item.get("draw", ""), "lost": item.get("lost", ""),
                "points": item.get("points", ""), "goals_for": item.get("goalsFor", ""),
                "goals_against": item.get("goalsAgainst", ""),
                "goal_difference": item.get("goalDifference", ""), "source": "football_data_org",
            })
    return pd.DataFrame(rows, columns=STANDING_COLUMNS)


def normalize_teams(payload: dict[str, Any], *, code: str, snapshot_id: str, captured_at: object) -> tuple[pd.DataFrame, pd.DataFrame]:
    captured = _timestamp(captured_at).isoformat()
    meta = COMPETITIONS[code]
    teams: list[dict[str, Any]] = []
    squads: list[dict[str, Any]] = []
    for item in payload.get("teams") or []:
        team_id = str(item.get("id") or "")
        coach = item.get("coach") or {}
        teams.append({
            "record_id": _record_id(snapshot_id, code, team_id), "snapshot_id": snapshot_id,
            "captured_at": captured, "competition_code": code, "competition_id": meta["competition_id"],
            "team_id": team_id, "team": item.get("name", ""), "short_name": item.get("shortName", ""),
            "tla": item.get("tla", ""), "coach_id": str(coach.get("id") or ""),
            "coach_name": coach.get("name", ""), "venue": item.get("venue", ""), "source": "football_data_org",
        })
        for player in item.get("squad") or []:
            player_id = str(player.get("id") or "")
            squads.append({
                "record_id": _record_id(snapshot_id, code, team_id, player_id), "snapshot_id": snapshot_id,
                "captured_at": captured, "competition_code": code, "competition_id": meta["competition_id"],
                "team_id": team_id, "team": item.get("name", ""), "player_id": player_id,
                "player": player.get("name", ""), "position": player.get("position", ""),
                "date_of_birth": player.get("dateOfBirth", ""), "nationality": player.get("nationality", ""),
                "source": "football_data_org",
            })
    return pd.DataFrame(teams, columns=TEAM_COLUMNS), pd.DataFrame(squads, columns=SQUAD_COLUMNS)


def _update_history(snapshot: pd.DataFrame, path: Path, columns: list[str]) -> int:
    history = pd.read_csv(path, low_memory=False) if path.exists() and path.stat().st_size else pd.DataFrame(columns=columns)
    combined = pd.concat([history, snapshot], ignore_index=True, sort=False).drop_duplicates("record_id", keep="last")
    combined = combined[columns]
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    combined.to_csv(part, index=False, encoding="utf-8-sig")
    part.replace(path)
    return int(len(combined))


def _read_history_latest(path: Path, *, columns: list[str], key: str) -> pd.DataFrame:
    if not path.exists() or not path.stat().st_size:
        return pd.DataFrame(columns=columns)
    frame = pd.read_csv(path, low_memory=False)
    frame["captured_at"] = pd.to_datetime(frame["captured_at"], errors="coerce", utc=True)
    return frame.sort_values("captured_at").drop_duplicates(key, keep="last")[columns]


def build_v2_result_supplement(matches: pd.DataFrame) -> pd.DataFrame:
    """Build result labels only; this is never a model-ready odds training table."""
    if matches.empty:
        return pd.DataFrame(columns=V2_RESULT_COLUMNS)
    frame = matches[matches["status"].eq("FINISHED")].copy()
    frame["home_goals"] = pd.to_numeric(frame["home_score"], errors="coerce")
    frame["away_goals"] = pd.to_numeric(frame["away_score"], errors="coerce")
    frame = frame[frame["home_goals"].notna() & frame["away_goals"].notna()].copy()
    frame["date"] = pd.to_datetime(frame["kickoff_at"], errors="coerce", utc=True).dt.date.astype(str)
    frame["actual_result"] = "D"
    frame.loc[frame["home_goals"] > frame["away_goals"], "actual_result"] = "H"
    frame.loc[frame["home_goals"] < frame["away_goals"], "actual_result"] = "A"
    frame["home_goals"] = frame["home_goals"].astype(int)
    frame["away_goals"] = frame["away_goals"].astype(int)
    return frame.rename(columns={"home_score": "_home_score", "away_score": "_away_score"})[V2_RESULT_COLUMNS]


def import_europe_incremental(
    *, client: Any, date_from: str, date_to: str, competitions: list[str], captured_at: object,
    output_root: str | Path, include_standings: bool = True, include_teams: bool = False,
) -> dict[str, Any]:
    captured = _timestamp(captured_at)
    invalid = sorted(set(competitions) - set(COMPETITIONS))
    if invalid:
        raise ValueError(f"unsupported football-data.org competitions: {invalid}")
    end_exclusive = (pd.Timestamp(date_to) + timedelta(days=1)).date().isoformat()
    payloads: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []
    try:
        payloads["matches"] = client.get("matches", {
            "competitions": ",".join(competitions), "dateFrom": date_from, "dateTo": end_exclusive,
        })
    except Exception as exc:
        failures.append({"feed": "matches", "error": str(exc)})
        payloads["matches"] = {"matches": []}
    for code in competitions:
        if include_standings:
            try:
                payloads[f"standings_{code}"] = client.get(f"competitions/{code}/standings")
            except Exception as exc:
                failures.append({"feed": f"standings_{code}", "error": str(exc)})
        if include_teams:
            try:
                payloads[f"teams_{code}"] = client.get(f"competitions/{code}/teams")
            except Exception as exc:
                failures.append({"feed": f"teams_{code}", "error": str(exc)})

    stamp = captured.tz_convert("UTC").strftime("%Y%m%dT%H%M%SZ")
    material = "".join(_digest(_canonical(payload)) for payload in payloads.values())
    snapshot_id = f"football_data_org_{stamp}_{_digest(material.encode())[:12]}"
    root = Path(output_root)
    raw_dir = root / "raw" / captured.tz_convert("Asia/Shanghai").date().isoformat() / snapshot_id
    raw_files: list[str] = []
    for name, payload in payloads.items():
        content = _canonical(payload)
        path = raw_dir / f"{name}_{_digest(content)[:12]}.json"
        _write_immutable(path, content)
        raw_files.append(str(path.resolve()))

    matches = normalize_matches(payloads["matches"], snapshot_id=snapshot_id, captured_at=captured)
    standing_frames = [normalize_standings(payloads[key], code=code, snapshot_id=snapshot_id, captured_at=captured)
                       for code in competitions if (key := f"standings_{code}") in payloads]
    standings = pd.concat(standing_frames, ignore_index=True) if standing_frames else pd.DataFrame(columns=STANDING_COLUMNS)
    team_frames: list[pd.DataFrame] = []
    squad_frames: list[pd.DataFrame] = []
    for code in competitions:
        key = f"teams_{code}"
        if key in payloads:
            teams, squads = normalize_teams(payloads[key], code=code, snapshot_id=snapshot_id, captured_at=captured)
            team_frames.append(teams); squad_frames.append(squads)
    teams = pd.concat(team_frames, ignore_index=True) if team_frames else pd.DataFrame(columns=TEAM_COLUMNS)
    squads = pd.concat(squad_frames, ignore_index=True) if squad_frames else pd.DataFrame(columns=SQUAD_COLUMNS)

    snapshot_dir = root / "snapshots" / captured.tz_convert("Asia/Shanghai").date().isoformat()
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    files = {"matches": (matches, MATCH_COLUMNS), "standings": (standings, STANDING_COLUMNS),
             "teams": (teams, TEAM_COLUMNS), "squads": (squads, SQUAD_COLUMNS)}
    paths: dict[str, str] = {}
    history_rows: dict[str, int] = {}
    for name, (frame, columns) in files.items():
        path = snapshot_dir / f"{snapshot_id}_{name}.csv"
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        paths[name] = str(path.resolve())
        if not frame.empty:
            history_rows[name] = _update_history(frame, root / f"{name}_history.csv", columns)

    latest = _read_history_latest(root / "matches_history.csv", columns=MATCH_COLUMNS, key="source_match_id")
    latest_path = root / "matches_latest.csv"
    latest.to_csv(latest_path, index=False, encoding="utf-8-sig")
    v2 = build_v2_result_supplement(latest)
    v2_path = root / "v2_incremental_results.csv"
    v2.to_csv(v2_path, index=False, encoding="utf-8-sig")
    return {
        "schema_version": 1, "source": "football_data_org", "status": "ok" if not failures else "partial",
        "snapshot_id": snapshot_id, "captured_at": captured.isoformat(), "date_from": date_from,
        "date_to": date_to, "competitions": competitions, "matches": int(len(matches)),
        "finished_matches": int(matches["status"].eq("FINISHED").sum()) if not matches.empty else 0,
        "standings": int(len(standings)), "teams": int(len(teams)), "squads": int(len(squads)),
        "failures": failures, "raw_files": raw_files, "snapshot_files": paths,
        "history_rows": history_rows, "matches_latest": str(latest_path.resolve()),
        "v2_incremental_results": str(v2_path.resolve()),
        "rate_limit_remaining": str(getattr(client, "last_headers", {}).get("X-Requests-Available-Minute", "")),
    }
