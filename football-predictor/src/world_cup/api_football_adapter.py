from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from world_cup.data import normalize_national_team


API_FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"
SOURCE = "api_football"


class ApiFootballClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = API_FOOTBALL_BASE_URL,
        timeout: int = 60,
    ) -> None:
        self.api_key = os.getenv("API_FOOTBALL_KEY", "") if api_key is None else api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = int(timeout)
        self.last_headers: dict[str, str] = {}

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("API_FOOTBALL_KEY is not configured")
        try:
            response = requests.get(
                f"{self.base_url}/{endpoint.lstrip('/')}",
                params=params or {},
                headers={"x-apisports-key": self.api_key},
                timeout=self.timeout,
            )
            self.last_headers = dict(response.headers)
            response.raise_for_status()
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detail = str(status) if status is not None else "network_error"
            raise RuntimeError(f"API-Football request failed ({detail})") from None
        return response.json()


def _api_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("response") or []
    return rows if isinstance(rows, list) else []


def fetch_world_cup_fixtures(
    client: ApiFootballClient,
    *,
    league_id: int,
    season: int,
    date: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"league": league_id, "season": season}
    if date:
        params["date"] = date
    return _api_rows(client.get("fixtures", params))


def fetch_fixture_injuries(
    client: ApiFootballClient,
    *,
    fixture_id: int | str,
) -> list[dict[str, Any]]:
    return _api_rows(client.get("injuries", {"fixture": fixture_id}))


def fetch_fixture_lineups(
    client: ApiFootballClient,
    *,
    fixture_id: int | str,
) -> list[dict[str, Any]]:
    return _api_rows(client.get("fixtures/lineups", {"fixture": fixture_id}))


def api_fixture_rows_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    out: list[dict[str, Any]] = []
    for item in rows:
        fixture = item.get("fixture") or {}
        teams = item.get("teams") or {}
        league = item.get("league") or {}
        fixture_id = str(fixture.get("id", "")).strip()
        if not fixture_id:
            continue
        out.append(
            {
                "source_fixture_id": fixture_id,
                "date": str(fixture.get("date", ""))[:10],
                "kickoff_time": str(fixture.get("date", "")),
                "home_team": normalize_national_team((teams.get("home") or {}).get("name", "")),
                "away_team": normalize_national_team((teams.get("away") or {}).get("name", "")),
                "venue": (fixture.get("venue") or {}).get("name", ""),
                "city": (fixture.get("venue") or {}).get("city", ""),
                "status": (fixture.get("status") or {}).get("short", ""),
                "league_id": league.get("id", ""),
                "league_name": league.get("name", ""),
                "season": league.get("season", ""),
                "source": SOURCE,
            }
        )
    return pd.DataFrame(out)


def injury_rows_to_absences(rows: list[dict[str, Any]]) -> pd.DataFrame:
    out: list[dict[str, Any]] = []
    for item in rows:
        fixture = item.get("fixture") or {}
        team = item.get("team") or {}
        player = item.get("player") or {}
        raw_type = str(player.get("type") or item.get("type") or "").strip().lower()
        reason = str(player.get("reason") or item.get("reason") or raw_type).strip()
        status = "suspended" if "suspend" in raw_type or "card" in reason.lower() else "injured"
        fixture_date = str(fixture.get("date", ""))[:10]
        out.append(
            {
                "date": fixture_date,
                "team": normalize_national_team(team.get("name", "")),
                "player": player.get("name", ""),
                "status": status,
                "impact": 1.0,
                "reason": reason,
                "source": SOURCE,
                "source_fixture_id": str(fixture.get("id", "")),
                "source_player_id": str(player.get("id", "")),
                "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            }
        )
    return pd.DataFrame(
        out,
        columns=[
            "date",
            "team",
            "player",
            "status",
            "impact",
            "reason",
            "source",
            "source_fixture_id",
            "source_player_id",
            "updated_at",
        ],
    )


def lineup_rows_to_realtime_lineups(
    rows: list[dict[str, Any]],
    *,
    fixture_id: int | str,
) -> pd.DataFrame:
    out: list[dict[str, Any]] = []
    for team_item in rows:
        team = normalize_national_team((team_item.get("team") or {}).get("name", ""))
        for player_item in team_item.get("startXI") or []:
            player = player_item.get("player") or {}
            out.append(
                {
                    "match_id": str(fixture_id),
                    "team": team,
                    "player": player.get("name", ""),
                    "role": "starter",
                    "confirmed": 1,
                    "source": SOURCE,
                    "source_player_id": str(player.get("id", "")),
                }
            )
        for player_item in team_item.get("substitutes") or []:
            player = player_item.get("player") or {}
            out.append(
                {
                    "match_id": str(fixture_id),
                    "team": team,
                    "player": player.get("name", ""),
                    "role": "substitute",
                    "confirmed": 1,
                    "source": SOURCE,
                    "source_player_id": str(player.get("id", "")),
                }
            )
    return pd.DataFrame(
        out,
        columns=[
            "match_id",
            "team",
            "player",
            "role",
            "confirmed",
            "source",
            "source_player_id",
        ],
    )


def import_api_football_realtime(
    *,
    output_dir: str | Path,
    league_id: int,
    season: int,
    date: str | None = None,
    api_key: str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    client = ApiFootballClient(api_key=api_key, timeout=timeout)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if not client.configured:
        for name, columns in {
            "fixtures.csv": [
                "source_fixture_id",
                "date",
                "kickoff_time",
                "home_team",
                "away_team",
                "venue",
                "city",
                "status",
                "league_id",
                "league_name",
                "season",
                "source",
            ],
            "absences.csv": [
                "date",
                "team",
                "player",
                "status",
                "impact",
                "reason",
                "source",
                "source_fixture_id",
                "source_player_id",
                "updated_at",
            ],
            "realtime_lineups.csv": [
                "match_id",
                "team",
                "player",
                "role",
                "confirmed",
                "source",
                "source_player_id",
            ],
        }.items():
            pd.DataFrame(columns=columns).to_csv(output / name, index=False)
        return {
            "source": SOURCE,
            "configured": False,
            "status": "skipped",
            "reason": "API_FOOTBALL_KEY is not configured",
            "output_dir": str(output),
        }

    fixtures_payload = fetch_world_cup_fixtures(
        client,
        league_id=league_id,
        season=season,
        date=date,
    )
    fixtures = api_fixture_rows_to_frame(fixtures_payload)
    fixtures.to_csv(output / "fixtures.csv", index=False)

    absence_frames: list[pd.DataFrame] = []
    lineup_frames: list[pd.DataFrame] = []
    failed: list[dict[str, str]] = []
    for fixture_id in fixtures["source_fixture_id"].astype(str).tolist():
        try:
            absence_frames.append(injury_rows_to_absences(fetch_fixture_injuries(client, fixture_id=fixture_id)))
        except Exception as exc:
            failed.append({"fixture_id": fixture_id, "feed": "injuries", "error": str(exc)})
        try:
            lineup_frames.append(
                lineup_rows_to_realtime_lineups(
                    fetch_fixture_lineups(client, fixture_id=fixture_id),
                    fixture_id=fixture_id,
                )
            )
        except Exception as exc:
            failed.append({"fixture_id": fixture_id, "feed": "lineups", "error": str(exc)})

    absences = pd.concat(absence_frames, ignore_index=True) if absence_frames else injury_rows_to_absences([])
    lineups = (
        pd.concat(lineup_frames, ignore_index=True)
        if lineup_frames
        else lineup_rows_to_realtime_lineups([], fixture_id="")
    )
    absences.to_csv(output / "absences.csv", index=False)
    lineups.to_csv(output / "realtime_lineups.csv", index=False)
    return {
        "source": SOURCE,
        "configured": True,
        "status": "ok",
        "league_id": league_id,
        "season": season,
        "date": date or "",
        "fixtures": int(len(fixtures)),
        "absence_rows": int(len(absences)),
        "lineup_rows": int(len(lineups)),
        "failed": failed,
        "output_dir": str(output),
    }
