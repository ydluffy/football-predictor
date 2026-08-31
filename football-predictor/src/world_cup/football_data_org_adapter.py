from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from world_cup.data import normalize_national_team


BASE_URL = "https://api.football-data.org/v4"
SOURCE = "football_data_org"


class FootballDataOrgClient:
    def __init__(
        self,
        *,
        api_token: str | None = None,
        base_url: str = BASE_URL,
        timeout: int = 60,
    ) -> None:
        # ``None`` means "use the process environment"; an explicit empty
        # string means "run unconfigured".  Keeping those cases distinct is
        # important for dry runs and tests on machines that have a project
        # credential loaded.
        self.api_token = (
            os.getenv("FOOTBALL_DATA_TOKEN", "")
            if api_token is None
            else str(api_token).strip()
        )
        self.base_url = base_url.rstrip("/")
        self.timeout = int(timeout)
        self.last_headers: dict[str, str] = {}

    @property
    def configured(self) -> bool:
        return bool(self.api_token)

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.api_token:
            raise RuntimeError("FOOTBALL_DATA_TOKEN is not configured")
        try:
            response = requests.get(
                f"{self.base_url}/{path.lstrip('/')}",
                params=params or {},
                headers={"X-Auth-Token": self.api_token},
                timeout=self.timeout,
            )
            self.last_headers = dict(response.headers)
            response.raise_for_status()
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detail = str(status) if status is not None else "network_error"
            raise RuntimeError(f"football-data.org request failed ({detail})") from None
        return response.json()


def fetch_world_cup_matches(
    client: FootballDataOrgClient,
    *,
    season: int,
) -> dict[str, Any]:
    return client.get("competitions/WC/matches", {"season": season})


def fetch_world_cup_teams(
    client: FootballDataOrgClient,
    *,
    season: int,
) -> dict[str, Any]:
    return client.get("competitions/WC/teams", {"season": season})


def matches_payload_to_fixtures(payload: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for item in payload.get("matches") or []:
        home = item.get("homeTeam") or {}
        away = item.get("awayTeam") or {}
        score = item.get("score") or {}
        full_time = score.get("fullTime") or {}
        utc_date = str(item.get("utcDate") or "")
        rows.append(
            {
                "match_id": str(item.get("id", "")),
                "date": utc_date[:10],
                "kickoff_time": utc_date,
                "home_team": normalize_national_team(home.get("name", "")),
                "away_team": normalize_national_team(away.get("name", "")),
                "status": item.get("status", ""),
                "matchday": item.get("matchday", ""),
                "stage": item.get("stage", ""),
                "group": item.get("group", ""),
                "home_score": full_time.get("home", ""),
                "away_score": full_time.get("away", ""),
                "winner": score.get("winner", ""),
                "last_updated": item.get("lastUpdated", ""),
                "source": SOURCE,
            }
        )
    return pd.DataFrame(rows)


def teams_payload_to_tables(payload: dict[str, Any], *, snapshot_date: str) -> dict[str, pd.DataFrame]:
    players: list[dict[str, object]] = []
    aliases: list[dict[str, object]] = []
    squads: list[dict[str, object]] = []
    coaches: list[dict[str, object]] = []
    teams: list[dict[str, object]] = []
    for team in payload.get("teams") or []:
        team_name = normalize_national_team(team.get("name", ""))
        team_id = str(team.get("id", ""))
        coach = team.get("coach") or {}
        teams.append(
            {
                "team": team_name,
                "source_team_id": team_id,
                "name": team.get("name", ""),
                "short_name": team.get("shortName", ""),
                "tla": team.get("tla", ""),
                "crest": team.get("crest", ""),
                "founded": team.get("founded", ""),
                "club_colors": team.get("clubColors", ""),
                "venue": team.get("venue", ""),
                "source": SOURCE,
            }
        )
        if coach:
            coaches.append(
                {
                    "snapshot_date": snapshot_date,
                    "team": team_name,
                    "coach_id": str(coach.get("id", "")),
                    "coach_name": coach.get("name", ""),
                    "date_of_birth": coach.get("dateOfBirth", ""),
                    "nationality": coach.get("nationality", ""),
                    "contract_start": (coach.get("contract") or {}).get("start", ""),
                    "contract_until": (coach.get("contract") or {}).get("until", ""),
                    "source": SOURCE,
                }
            )
        for player in team.get("squad") or []:
            source_player_id = str(player.get("id", ""))
            if not source_player_id:
                continue
            player_id = f"football_data_{source_player_id}"
            players.append(
                {
                    "player_id": player_id,
                    "canonical_name": player.get("name", ""),
                    "national_team": team_name,
                    "date_of_birth": player.get("dateOfBirth", ""),
                    "primary_position": player.get("position", ""),
                }
            )
            aliases.append(
                {
                    "source": SOURCE,
                    "source_player_id": source_player_id,
                    "source_name": player.get("name", ""),
                    "player_id": player_id,
                }
            )
            squads.append(
                {
                    "snapshot_date": snapshot_date,
                    "team": team_name,
                    "player_id": player_id,
                    "role": "squad",
                    "position": player.get("position", ""),
                    "club": "",
                }
            )
    return {
        "teams": pd.DataFrame(teams),
        "coaches": pd.DataFrame(coaches),
        "players": pd.DataFrame(players),
        "player_aliases": pd.DataFrame(aliases),
        "squads": pd.DataFrame(squads),
    }


def _write_empty_outputs(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        columns=[
            "match_id",
            "date",
            "kickoff_time",
            "home_team",
            "away_team",
            "status",
            "matchday",
            "stage",
            "group",
            "home_score",
            "away_score",
            "winner",
            "last_updated",
            "source",
        ]
    ).to_csv(output_dir / "fixtures.csv", index=False)
    pd.DataFrame(columns=["team", "source_team_id", "name", "short_name", "tla"]).to_csv(
        output_dir / "teams.csv",
        index=False,
    )
    pd.DataFrame(
        columns=["snapshot_date", "team", "coach_id", "coach_name", "date_of_birth", "nationality", "source"]
    ).to_csv(output_dir / "coaches.csv", index=False)
    pd.DataFrame(
        columns=["player_id", "canonical_name", "national_team", "date_of_birth", "primary_position"]
    ).to_csv(output_dir / "players.csv", index=False)
    pd.DataFrame(columns=["source", "source_player_id", "source_name", "player_id"]).to_csv(
        output_dir / "player_aliases.csv",
        index=False,
    )
    pd.DataFrame(columns=["snapshot_date", "team", "player_id", "role", "position", "club"]).to_csv(
        output_dir / "squads.csv",
        index=False,
    )


def import_football_data_world_cup(
    *,
    output_dir: str | Path,
    season: int,
    api_token: str | None = None,
    timeout: int = 60,
    snapshot_date: str | None = None,
) -> dict[str, Any]:
    client = FootballDataOrgClient(api_token=api_token, timeout=timeout)
    output = Path(output_dir)
    if not client.configured:
        _write_empty_outputs(output)
        return {
            "source": SOURCE,
            "configured": False,
            "status": "skipped",
            "reason": "FOOTBALL_DATA_TOKEN is not configured",
            "output_dir": str(output),
        }
    output.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot_date or datetime.now(timezone.utc).date().isoformat()
    matches_payload = fetch_world_cup_matches(client, season=season)
    teams_payload = fetch_world_cup_teams(client, season=season)
    fixtures = matches_payload_to_fixtures(matches_payload)
    tables = teams_payload_to_tables(teams_payload, snapshot_date=snapshot)
    fixtures.to_csv(output / "fixtures.csv", index=False)
    for name, frame in tables.items():
        frame.to_csv(output / f"{name}.csv", index=False)
    return {
        "source": SOURCE,
        "configured": True,
        "status": "ok",
        "season": season,
        "fixtures": int(len(fixtures)),
        "teams": int(len(tables["teams"])),
        "players": int(len(tables["players"])),
        "coaches": int(len(tables["coaches"])),
        "output_dir": str(output),
        "requests_available_minute_not_captured": True,
    }
