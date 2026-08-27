from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from world_cup.data import normalize_national_team


SPORTMONKS_BASE_URL = "https://api.sportmonks.com/v3/football"
SOURCE = "sportmonks"


class SportMonksClient:
    def __init__(
        self,
        *,
        api_token: str | None = None,
        base_url: str = SPORTMONKS_BASE_URL,
        timeout: int = 60,
    ) -> None:
        self.api_token = (
            os.getenv("SPORTMONKS_API_TOKEN", "")
            if api_token is None
            else api_token
        )
        self.base_url = base_url.rstrip("/")
        self.timeout = int(timeout)

    @property
    def configured(self) -> bool:
        return bool(self.api_token)

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.api_token:
            raise RuntimeError("SPORTMONKS_API_TOKEN is not configured")
        request_params = dict(params or {})
        try:
            response = requests.get(
                f"{self.base_url}/{endpoint.lstrip('/')}",
                params=request_params,
                headers={"Authorization": self.api_token},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detail = str(status) if status is not None else "network_error"
            raise RuntimeError(f"SportMonks request failed ({detail})") from None
        return response.json()


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") or []
    return data if isinstance(data, list) else [data]


def _included_list(item: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = item.get(key)
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        data = value.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    return []


def fetch_world_cup_fixtures(
    client: SportMonksClient,
    *,
    season_id: int | str,
    date_from: str = "",
    date_to: str = "",
    include: str = "participants;venue;state",
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"include": include}
    if date_from and date_to:
        rows = _items(client.get(f"fixtures/between/{date_from}/{date_to}", params))
        expected_season = str(season_id)
        return [row for row in rows if str(row.get("season_id", "")) == expected_season]
    return _items(client.get(f"seasons/{season_id}/fixtures", params))


def fetch_fixture_realtime(
    client: SportMonksClient,
    *,
    fixture_id: int | str,
    include: str = "participants;lineups;sidelined;formations;state",
) -> dict[str, Any]:
    payload = client.get(f"fixtures/{fixture_id}", {"include": include})
    items = _items(payload)
    return items[0] if items else {}


def _participant_names(fixture: dict[str, Any]) -> tuple[str, str]:
    participants = _included_list(fixture, "participants")
    home = ""
    away = ""
    for participant in participants:
        meta = participant.get("meta") or {}
        location = str(meta.get("location", "")).lower()
        name = participant.get("name") or participant.get("short_code") or ""
        if location == "home":
            home = str(name)
        elif location == "away":
            away = str(name)
    return normalize_national_team(home), normalize_national_team(away)


def sportmonks_fixture_rows_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    out: list[dict[str, Any]] = []
    for item in rows:
        fixture_id = str(item.get("id", "")).strip()
        if not fixture_id:
            continue
        home_team, away_team = _participant_names(item)
        starting_at = item.get("starting_at") or ""
        out.append(
            {
                "source_fixture_id": fixture_id,
                "date": str(starting_at)[:10],
                "kickoff_time": starting_at,
                "home_team": home_team,
                "away_team": away_team,
                "venue": (item.get("venue") or {}).get("name", "")
                if isinstance(item.get("venue"), dict)
                else "",
                "status": (item.get("state") or {}).get("name", "")
                if isinstance(item.get("state"), dict)
                else "",
                "source": SOURCE,
            }
        )
    return pd.DataFrame(
        out,
        columns=[
            "source_fixture_id",
            "date",
            "kickoff_time",
            "home_team",
            "away_team",
            "venue",
            "status",
            "source",
        ],
    )


def _player_name(row: dict[str, Any]) -> str:
    player = row.get("player")
    if isinstance(player, dict):
        return str(player.get("display_name") or player.get("name") or player.get("common_name") or "")
    return str(row.get("player_name") or row.get("name") or "")


def _team_name(row: dict[str, Any]) -> str:
    team = row.get("team")
    if isinstance(team, dict):
        return normalize_national_team(team.get("name", ""))
    participant = row.get("participant")
    if isinstance(participant, dict):
        return normalize_national_team(participant.get("name", ""))
    return normalize_national_team(row.get("team_name", ""))


def sidelined_rows_to_absences(
    rows: list[dict[str, Any]],
    *,
    fixture: dict[str, Any] | None = None,
) -> pd.DataFrame:
    fixture = fixture or {}
    fixture_date = str(fixture.get("starting_at") or "")[:10]
    out: list[dict[str, Any]] = []
    for item in rows:
        reason = str(
            item.get("reason")
            or item.get("category")
            or item.get("type")
            or item.get("description")
            or ""
        ).strip()
        raw_status = str(item.get("type") or item.get("category") or reason).lower()
        status = "suspended" if "suspend" in raw_status or "card" in reason.lower() else "injured"
        out.append(
            {
                "date": str(item.get("date") or fixture_date)[:10],
                "team": _team_name(item),
                "player": _player_name(item),
                "status": status,
                "impact": 1.0,
                "reason": reason,
                "source": SOURCE,
                "source_fixture_id": str(fixture.get("id", "") or item.get("fixture_id", "")),
                "source_player_id": str(item.get("player_id", "")),
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
    for item in rows:
        formation_position = str(item.get("formation_position") or item.get("position") or "").strip()
        is_starter = bool(item.get("type_id") == 11 or item.get("starting") or formation_position)
        role = "starter" if is_starter else "substitute"
        out.append(
            {
                "match_id": str(fixture_id),
                "team": _team_name(item),
                "player": _player_name(item),
                "role": role,
                "confirmed": 1,
                "source": SOURCE,
                "source_player_id": str(item.get("player_id", "")),
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


def _empty_outputs(output: Path) -> None:
    sportmonks_fixture_rows_to_frame([]).to_csv(output / "fixtures.csv", index=False)
    sidelined_rows_to_absences([]).to_csv(output / "absences.csv", index=False)
    lineup_rows_to_realtime_lineups([], fixture_id="").to_csv(
        output / "realtime_lineups.csv",
        index=False,
    )


def import_sportmonks_world_cup_realtime(
    *,
    output_dir: str | Path,
    season_id: int | str,
    date_from: str = "",
    date_to: str = "",
    api_token: str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    client = SportMonksClient(api_token=api_token, timeout=timeout)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if not client.configured:
        _empty_outputs(output)
        return {
            "source": SOURCE,
            "configured": False,
            "status": "skipped",
            "reason": "SPORTMONKS_API_TOKEN is not configured",
            "output_dir": str(output),
        }

    fixture_payload = fetch_world_cup_fixtures(
        client,
        season_id=season_id,
        date_from=date_from,
        date_to=date_to,
    )
    fixtures = sportmonks_fixture_rows_to_frame(fixture_payload)
    fixtures.to_csv(output / "fixtures.csv", index=False)

    absence_frames: list[pd.DataFrame] = []
    lineup_frames: list[pd.DataFrame] = []
    failed: list[dict[str, str]] = []
    for fixture_id in fixtures["source_fixture_id"].astype(str).tolist():
        try:
            detail = fetch_fixture_realtime(client, fixture_id=fixture_id)
            absence_frames.append(
                sidelined_rows_to_absences(
                    _included_list(detail, "sidelined"),
                    fixture=detail,
                )
            )
            lineup_frames.append(
                lineup_rows_to_realtime_lineups(
                    _included_list(detail, "lineups"),
                    fixture_id=fixture_id,
                )
            )
        except Exception as exc:
            failed.append({"fixture_id": fixture_id, "error": str(exc)})

    absences = pd.concat(absence_frames, ignore_index=True) if absence_frames else sidelined_rows_to_absences([])
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
        "season_id": str(season_id),
        "date_from": date_from,
        "date_to": date_to,
        "fixtures": int(len(fixtures)),
        "absence_rows": int(len(absences)),
        "lineup_rows": int(len(lineups)),
        "failed": failed,
        "output_dir": str(output),
    }
