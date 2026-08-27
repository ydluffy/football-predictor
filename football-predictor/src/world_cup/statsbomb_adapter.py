from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

from world_cup.data import normalize_national_team


RAW_ROOT = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"


def _download_json(url: str, destination: Path, *, timeout: int = 90) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            payload = response.content
            json.loads(payload.decode("utf-8"))
            temporary.write_bytes(payload)
            os.replace(temporary, destination)
            return
        except Exception as exc:
            last_error = exc
            temporary.unlink(missing_ok=True)
            time.sleep(2**attempt)
    raise RuntimeError(f"failed to download {url}") from last_error


def download_statsbomb_world_cup_lineups(
    cache_dir: str | Path,
    *,
    seasons: tuple[tuple[int, int], ...] = ((43, 3), (43, 106)),
) -> dict[str, object]:
    root = Path(cache_dir)
    matches_dir = root / "matches"
    lineups_dir = root / "lineups"
    match_count = 0
    downloaded = 0
    for competition_id, season_id in seasons:
        matches_path = matches_dir / f"{competition_id}_{season_id}.json"
        if not matches_path.exists():
            _download_json(
                f"{RAW_ROOT}/matches/{competition_id}/{season_id}.json",
                matches_path,
            )
        matches = json.loads(matches_path.read_text(encoding="utf-8"))
        match_count += len(matches)
        for match in matches:
            match_id = int(match["match_id"])
            lineup_path = lineups_dir / f"{match_id}.json"
            if lineup_path.exists():
                continue
            _download_json(f"{RAW_ROOT}/lineups/{match_id}.json", lineup_path)
            downloaded += 1
    files = sorted(root.rglob("*.json"))
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.relative_to(root).as_posix().encode("utf-8"))
        digest.update(file.read_bytes())
    return {
        "matches": match_count,
        "lineup_files": len(list(lineups_dir.glob("*.json"))),
        "downloaded": downloaded,
        "sha256": digest.hexdigest(),
        "source": "https://github.com/statsbomb/open-data",
    }


def _position_minutes(positions: list[dict[str, object]]) -> float:
    intervals = []
    for position in positions:
        start = str(position.get("from", "00:00"))
        end = str(position.get("to") or "90:00")
        start_minute, start_second = (int(value) for value in start.split(":")[:2])
        end_minute, end_second = (int(value) for value in end.split(":")[:2])
        start_value = start_minute + start_second / 60.0
        end_value = end_minute + end_second / 60.0
        if end_value > start_value:
            intervals.append((start_value, end_value))
    if not intervals:
        return 0.0
    intervals.sort()
    merged = [intervals[0]]
    for start_value, end_value in intervals[1:]:
        previous_start, previous_end = merged[-1]
        if start_value <= previous_end:
            merged[-1] = (previous_start, max(previous_end, end_value))
        else:
            merged.append((start_value, end_value))
    return float(sum(end - start for start, end in merged))


def convert_statsbomb_to_player_contract(
    cache_dir: str | Path,
    output_dir: str | Path,
) -> dict[str, object]:
    root = Path(cache_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    player_rows: dict[str, dict[str, object]] = {}
    alias_rows: dict[tuple[str, str], dict[str, object]] = {}
    squad_rows = []
    national_rows = []
    fixture_rows = []

    for matches_path in sorted((root / "matches").glob("*.json")):
        matches = json.loads(matches_path.read_text(encoding="utf-8"))
        for match in matches:
            match_id = int(match["match_id"])
            match_date = str(match["match_date"])
            home = normalize_national_team(match["home_team"]["home_team_name"])
            away = normalize_national_team(match["away_team"]["away_team_name"])
            fixture_rows.append(
                {
                    "match_id": match_id,
                    "date": match_date,
                    "home_team": home,
                    "away_team": away,
                    "home_score": match.get("home_score"),
                    "away_score": match.get("away_score"),
                }
            )
            lineups = json.loads(
                (root / "lineups" / f"{match_id}.json").read_text(encoding="utf-8")
            )
            for team_lineup in lineups:
                team = normalize_national_team(team_lineup["team_name"])
                opponent = away if team == home else home
                for player in team_lineup["lineup"]:
                    source_id = str(player["player_id"])
                    player_id = f"statsbomb_{source_id}"
                    name = str(player["player_name"])
                    positions = player.get("positions") or []
                    started = any(
                        position.get("start_reason") == "Starting XI"
                        for position in positions
                    )
                    role = "starter" if started else "substitute"
                    position_name = (
                        str(positions[0].get("position", "Unknown"))
                        if positions
                        else "Unknown"
                    )
                    minutes = _position_minutes(positions)
                    player_rows[player_id] = {
                        "player_id": player_id,
                        "canonical_name": name,
                        "national_team": team,
                        "date_of_birth": "",
                        "primary_position": position_name,
                    }
                    alias_rows[("statsbomb", source_id)] = {
                        "source": "statsbomb",
                        "source_player_id": source_id,
                        "source_name": name,
                        "player_id": player_id,
                    }
                    squad_rows.append(
                        {
                            "snapshot_date": match_date,
                            "team": team,
                            "player_id": player_id,
                            "role": role,
                            "position": position_name,
                            "club": "",
                        }
                    )
                    national_rows.append(
                        {
                            "match_date": match_date,
                            "team": team,
                            "opponent": opponent,
                            "player_id": player_id,
                            "started": started,
                            "minutes": minutes,
                        }
                    )

    players = pd.DataFrame(player_rows.values()).sort_values("player_id")
    aliases = pd.DataFrame(alias_rows.values()).sort_values(
        ["source", "source_player_id"]
    )
    squads = pd.DataFrame(squad_rows).drop_duplicates(
        ["snapshot_date", "team", "player_id"]
    )
    national = pd.DataFrame(national_rows).drop_duplicates(
        ["match_date", "team", "opponent", "player_id"]
    )
    fixtures = pd.DataFrame(fixture_rows).drop_duplicates("match_id")
    availability = pd.DataFrame(
        columns=["as_of_date", "team", "player_id", "status", "reason"]
    )
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
    players.to_csv(output / "players.csv", index=False)
    aliases.to_csv(output / "player_aliases.csv", index=False)
    squads.to_csv(output / "squads.csv", index=False)
    availability.to_csv(output / "availability.csv", index=False)
    club.to_csv(output / "club_appearances.csv", index=False)
    national.to_csv(output / "national_appearances.csv", index=False)
    fixtures.to_csv(output / "fixtures.csv", index=False)
    starter_counts = (
        squads[squads["role"].eq("starter")]
        .groupby(["snapshot_date", "team"])
        .size()
    )
    return {
        "players": int(len(players)),
        "aliases": int(len(aliases)),
        "squad_rows": int(len(squads)),
        "national_appearance_rows": int(len(national)),
        "fixtures": int(len(fixtures)),
        "team_match_lineups": int(len(starter_counts)),
        "lineups_with_11_starters": int(starter_counts.eq(11).sum()),
        "lineup_11_starter_rate": float(starter_counts.eq(11).mean()),
        "minutes_non_null_rate": float(national["minutes"].notna().mean()),
        "availability_rows": 0,
        "club_appearance_rows": 0,
        "seasons": sorted(squads["snapshot_date"].str[:4].unique().tolist()),
    }
