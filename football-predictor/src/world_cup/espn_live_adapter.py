from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from world_cup.data import normalize_national_team


BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"
SOURCE = "espn_public"


def _ref_last_segment(value: object) -> str:
    text = str((value or {}).get("$ref") if isinstance(value, dict) else value or "")
    if not text:
        return ""
    path = text.split("?", 1)[0].rstrip("/")
    return path.rsplit("/", 1)[-1]


def _athlete_club_id(athlete: dict) -> str:
    team_id = _ref_last_segment(athlete.get("defaultTeam"))
    league_slug = _ref_last_segment(athlete.get("defaultLeague"))
    if not team_id or league_slug.startswith("fifa."):
        return ""
    return f"{league_slug}:{team_id}" if league_slug else team_id


def _download_json(url: str, destination: Path, *, timeout: int = 60) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(temporary, destination)
            return payload
        except Exception as exc:
            last_error = exc
            temporary.unlink(missing_ok=True)
            time.sleep(2**attempt)
    raise RuntimeError(f"failed to download {url}") from last_error


def _player_id(source_id: object) -> str:
    return f"espn_{str(source_id).strip()}"


def _athlete_row(athlete: dict, team: str) -> dict[str, object]:
    position = athlete.get("position") or {}
    return {
        "player_id": _player_id(athlete["id"]),
        "canonical_name": athlete.get("displayName") or athlete.get("fullName"),
        "national_team": team,
        "date_of_birth": str(athlete.get("dateOfBirth") or "")[:10],
        "primary_position": position.get("displayName") or position.get("name") or "",
    }


def _alias_row(athlete: dict) -> dict[str, object]:
    return {
        "source": SOURCE,
        "source_player_id": str(athlete["id"]),
        "source_name": athlete.get("displayName") or athlete.get("fullName"),
        "player_id": _player_id(athlete["id"]),
    }


def _injury_status(value: object) -> str:
    text = str(value or "").casefold()
    if "suspend" in text:
        return "suspended"
    if any(word in text for word in ("doubt", "questionable", "day-to-day")):
        return "doubtful"
    if any(word in text for word in ("out", "injur", "inactive")):
        return "injured"
    return "unavailable"


def parse_team_roster(
    payload: dict,
    *,
    snapshot_date: str,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    team = normalize_national_team(payload["team"]["displayName"])
    players: list[dict] = []
    aliases: list[dict] = []
    squads: list[dict] = []
    affiliations: list[dict] = []
    for athlete in payload.get("athletes") or []:
        if not athlete.get("id"):
            continue
        players.append(_athlete_row(athlete, team))
        aliases.append(_alias_row(athlete))
        position = athlete.get("position") or {}
        club_id = _athlete_club_id(athlete)
        league_slug = _ref_last_segment(athlete.get("defaultLeague"))
        squads.append(
            {
                "snapshot_date": snapshot_date,
                "team": team,
                "player_id": _player_id(athlete["id"]),
                "role": "squad",
                "position": position.get("displayName") or position.get("name") or "",
                "club": club_id,
            }
        )
        affiliations.append(
            {
                "snapshot_date": snapshot_date,
                "team": team,
                "player_id": _player_id(athlete["id"]),
                "club_id": club_id,
                "league_slug": league_slug,
                "source": SOURCE,
            }
        )
    return players, aliases, squads, affiliations


def parse_match_summary(
    payload: dict,
    *,
    fetched_date: str,
) -> dict[str, list[dict]]:
    header = payload.get("header") or {}
    competition = (header.get("competitions") or [{}])[0]
    event_date = str(competition.get("date") or fetched_date)[:10]
    competitors = competition.get("competitors") or []
    team_by_id = {
        str(item.get("team", {}).get("id")): normalize_national_team(
            item.get("team", {}).get("displayName", "")
        )
        for item in competitors
    }
    opponent_by_team = {}
    names = [name for name in team_by_id.values() if name]
    if len(names) == 2:
        opponent_by_team = {names[0]: names[1], names[1]: names[0]}

    players: list[dict] = []
    aliases: list[dict] = []
    squads: list[dict] = []
    appearances: list[dict] = []
    availability: list[dict] = []

    for roster in payload.get("rosters") or []:
        team_payload = roster.get("team") or {}
        team = team_by_id.get(str(team_payload.get("id"))) or normalize_national_team(
            team_payload.get("displayName", "")
        )
        entries = roster.get("roster") or []
        lineup_confirmed = sum(bool(entry.get("starter")) for entry in entries) == 11
        for entry in entries:
            athlete = entry.get("athlete") or {}
            if not athlete.get("id"):
                continue
            player = _athlete_row(athlete, team)
            players.append(player)
            aliases.append(_alias_row(athlete))
            position = entry.get("position") or athlete.get("position") or {}
            role = (
                "starter"
                if lineup_confirmed and entry.get("starter")
                else "substitute"
                if lineup_confirmed
                else "squad"
            )
            squads.append(
                {
                    "snapshot_date": event_date,
                    "team": team,
                    "player_id": player["player_id"],
                    "role": role,
                    "position": position.get("displayName") or position.get("name") or "",
                    "club": "",
                }
            )
            if competition.get("status", {}).get("type", {}).get("completed"):
                stats = {
                    stat.get("name"): stat.get("value")
                    for stat in entry.get("stats") or []
                }
                minutes = stats.get("minutesPlayed")
                if minutes is None:
                    minutes = 90 if entry.get("starter") else 0
                appearances.append(
                    {
                        "match_date": event_date,
                        "team": team,
                        "opponent": opponent_by_team.get(team, ""),
                        "player_id": player["player_id"],
                        "started": bool(entry.get("starter")),
                        "minutes": min(float(minutes), 130.0),
                    }
                )

    for group in payload.get("injuries") or []:
        team_payload = group.get("team") or {}
        team = team_by_id.get(str(team_payload.get("id"))) or normalize_national_team(
            team_payload.get("displayName", "")
        )
        for item in group.get("injuries") or group.get("items") or []:
            athlete = item.get("athlete") or {}
            if not athlete.get("id"):
                continue
            players.append(_athlete_row(athlete, team))
            aliases.append(_alias_row(athlete))
            detail = item.get("details") or {}
            status_text = (
                item.get("status")
                or item.get("type")
                or detail.get("type")
                or detail.get("status")
            )
            reason = (
                item.get("description")
                or detail.get("detail")
                or detail.get("description")
                or str(status_text or "")
            )
            availability.append(
                {
                    "as_of_date": fetched_date,
                    "team": team,
                    "player_id": _player_id(athlete["id"]),
                    "status": _injury_status(status_text),
                    "reason": reason,
                }
            )

    return {
        "players": players,
        "aliases": aliases,
        "squads": squads,
        "availability": availability,
        "national_appearances": appearances,
    }


def import_espn_world_cup_live(
    cache_dir: str | Path,
    output_dir: str | Path,
    *,
    as_of_date: str | None = None,
    download: bool = True,
) -> dict[str, object]:
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    snapshot_date = as_of_date or fetched_at[:10]
    cache = Path(cache_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    scoreboard_url = f"{BASE_URL}/scoreboard?dates=2026&limit=200"
    scoreboard_path = cache / "scoreboard_2026.json"
    scoreboard = (
        _download_json(scoreboard_url, scoreboard_path)
        if download
        else json.loads(scoreboard_path.read_text(encoding="utf-8"))
    )
    events = scoreboard.get("events") or []
    teams: dict[str, str] = {}
    for event in events:
        for competitor in event["competitions"][0].get("competitors") or []:
            team = competitor["team"]
            teams[str(team["id"])] = team["displayName"]

    rows = {
        "players": [],
        "aliases": [],
        "squads": [],
        "availability": [],
        "national_appearances": [],
        "club_affiliations": [],
    }
    source_rows = [
        {
            "source_type": "schedule",
            "source_url": scoreboard_url,
            "fetched_at": fetched_at,
            "record_id": "2026",
        }
    ]
    teams_with_rosters = 0
    for team_id in sorted(teams, key=int):
        url = f"{BASE_URL}/teams/{team_id}/roster"
        path = cache / "teams" / f"{team_id}.json"
        payload = (
            _download_json(url, path)
            if download
            else json.loads(path.read_text(encoding="utf-8"))
        )
        players, aliases, squads, affiliations = parse_team_roster(
            payload,
            snapshot_date=snapshot_date,
        )
        if players:
            teams_with_rosters += 1
        rows["players"].extend(players)
        rows["aliases"].extend(aliases)
        rows["squads"].extend(squads)
        rows["club_affiliations"].extend(affiliations)
        source_rows.append(
            {
                "source_type": "team_roster",
                "source_url": url,
                "fetched_at": fetched_at,
                "record_id": team_id,
            }
        )

    imported_events = 0
    confirmed_lineups = 0
    completed_events = 0
    missing_summary_event_ids: list[str] = []
    for event in events:
        event_date = str(event.get("date", ""))[:10]
        if event_date > snapshot_date:
            continue
        event_id = str(event["id"])
        url = f"{BASE_URL}/summary?event={event_id}"
        path = cache / "summaries" / f"{event_id}.json"
        if not download and not path.exists():
            missing_summary_event_ids.append(event_id)
            continue
        payload = (
            _download_json(url, path)
            if download
            else json.loads(path.read_text(encoding="utf-8"))
        )
        parsed = parse_match_summary(payload, fetched_date=snapshot_date)
        for key in (
            "players",
            "aliases",
            "squads",
            "availability",
            "national_appearances",
        ):
            rows[key].extend(parsed[key])
        imported_events += 1
        if event.get("status", {}).get("type", {}).get("completed"):
            completed_events += 1
        counts = (
            pd.DataFrame(parsed["squads"])
            .query("role == 'starter'")
            .groupby("team")
            .size()
            if parsed["squads"]
            else pd.Series(dtype=int)
        )
        confirmed_lineups += int(counts.eq(11).sum())
        source_rows.append(
            {
                "source_type": "match_summary",
                "source_url": url,
                "fetched_at": fetched_at,
                "record_id": event_id,
            }
        )

    players = pd.DataFrame(rows["players"]).drop_duplicates("player_id", keep="last")
    aliases = pd.DataFrame(rows["aliases"]).drop_duplicates(
        ["source", "source_player_id"], keep="last"
    )
    squads = pd.DataFrame(rows["squads"])
    club_lookup = (
        pd.DataFrame(rows["club_affiliations"])
        .dropna(subset=["player_id"])
        .drop_duplicates("player_id", keep="last")
        .set_index("player_id")["club_id"]
        .to_dict()
        if rows["club_affiliations"]
        else {}
    )
    if not squads.empty:
        squads["club"] = squads.apply(
            lambda row: row["club"]
            if str(row.get("club", "")).strip()
            else club_lookup.get(str(row["player_id"]), ""),
            axis=1,
        )
    role_priority = {"squad": 0, "substitute": 1, "starter": 2}
    squads["_priority"] = squads["role"].map(role_priority)
    squads = (
        squads.sort_values("_priority")
        .drop_duplicates(["snapshot_date", "team", "player_id"], keep="last")
        .drop(columns="_priority")
    )
    availability = pd.DataFrame(
        rows["availability"],
        columns=["as_of_date", "team", "player_id", "status", "reason"],
    ).drop_duplicates(["as_of_date", "team", "player_id"], keep="last")
    national = pd.DataFrame(
        rows["national_appearances"],
        columns=[
            "match_date",
            "team",
            "opponent",
            "player_id",
            "started",
            "minutes",
        ],
    ).drop_duplicates(["match_date", "team", "opponent", "player_id"], keep="last")
    club = pd.DataFrame(
        columns=[
            "match_date",
            "player_id",
            "club",
            "competition",
            "minutes",
            "started",
            "goals",
            "assists",
            "xg",
            "xa",
        ]
    )
    affiliations = pd.DataFrame(
        rows["club_affiliations"],
        columns=[
            "snapshot_date",
            "team",
            "player_id",
            "club_id",
            "league_slug",
            "source",
        ],
    ).drop_duplicates(["snapshot_date", "team", "player_id"], keep="last")
    fixtures = pd.DataFrame(
        [
            {
                "match_id": event["id"],
                "date": str(event["date"])[:10],
                "home_team": normalize_national_team(
                    next(
                        item["team"]["displayName"]
                        for item in event["competitions"][0]["competitors"]
                        if item["homeAway"] == "home"
                    )
                ),
                "away_team": normalize_national_team(
                    next(
                        item["team"]["displayName"]
                        for item in event["competitions"][0]["competitors"]
                        if item["homeAway"] == "away"
                    )
                ),
                "status": event["status"]["type"]["state"],
            }
            for event in events
        ]
    )

    players.to_csv(output / "players.csv", index=False)
    aliases.to_csv(output / "player_aliases.csv", index=False)
    squads.to_csv(output / "squads.csv", index=False)
    availability.to_csv(output / "availability.csv", index=False)
    club.to_csv(output / "club_appearances.csv", index=False)
    affiliations.to_csv(output / "club_affiliations.csv", index=False)
    national.to_csv(output / "national_appearances.csv", index=False)
    fixtures.to_csv(output / "fixtures.csv", index=False)
    pd.DataFrame(source_rows).to_csv(output / "source_snapshots.csv", index=False)

    return {
        "source": SOURCE,
        "source_is_official": False,
        "fetched_at": fetched_at,
        "team_ids_discovered": len(teams),
        "teams_with_current_rosters": teams_with_rosters,
        "current_roster_team_coverage": teams_with_rosters / 48,
        "players": len(players),
        "fixtures": len(fixtures),
        "summaries_imported": imported_events,
        "summaries_missing": len(missing_summary_event_ids),
        "missing_summary_event_ids": missing_summary_event_ids,
        "completed_matches": completed_events,
        "team_lineups_with_11_starters": confirmed_lineups,
        "summary_team_lineup_coverage": (
            confirmed_lineups / (imported_events * 2)
            if imported_events
            else 0.0
        ),
        "availability_rows": len(availability),
        "availability_player_coverage": (
            len(availability) / len(players) if len(players) else 0.0
        ),
        "club_affiliation_rows": len(affiliations),
        "club_affiliation_player_coverage": (
            affiliations["club_id"].astype(str).str.strip().ne("").sum() / len(players)
            if len(players) and not affiliations.empty
            else 0.0
        ),
        "club_appearance_rows": len(club),
        "club_appearance_player_coverage": 0.0,
        "unknown_is_not_available": True,
    }
