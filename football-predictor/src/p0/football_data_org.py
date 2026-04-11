from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib import error, parse, request


@dataclass(frozen=True)
class FootballDataOrgClient:
    api_key: str
    base_url: str = "https://api.football-data.org/v4"
    calls_per_minute: int = 10

    def _sleep_between_calls(self) -> None:
        if self.calls_per_minute <= 0:
            return
        time.sleep(max(0.0, 60.0 / float(self.calls_per_minute)))

    def _get_json(self, path: str, query: dict[str, str] | None = None) -> dict[str, Any]:
        url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        if query:
            url += "?" + parse.urlencode(query)
        req = request.Request(url)
        req.add_header("X-Auth-Token", self.api_key)
        req.add_header("Accept", "application/json")
        try:
            with request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
            raise RuntimeError(f"football-data.org http_error status={getattr(e,'code',None)} body={body[:500]}")
        return json.loads(raw)

    def fetch_matches(self, competition_code: str, date_from: str, date_to: str) -> list[dict[str, Any]]:
        payload = self._get_json(
            f"competitions/{competition_code}/matches",
            {"dateFrom": date_from, "dateTo": date_to},
        )
        self._sleep_between_calls()
        matches = payload.get("matches", [])
        out: list[dict[str, Any]] = []
        for m in matches:
            fixture_id = m.get("id")
            if fixture_id is None:
                continue
            competition = m.get("competition") or {}
            season = m.get("season") or {}
            score = m.get("score") or {}
            ft = (score.get("fullTime") or {}) if isinstance(score, dict) else {}
            home = m.get("homeTeam") or {}
            away = m.get("awayTeam") or {}
            out.append(
                {
                    "fixture_id": int(fixture_id),
                    "competition_code": competition_code,
                    "competition_name": competition.get("name"),
                    "season": season.get("startDate", "")[:4] and int(season.get("startDate", "")[:4]) or None,
                    "matchday": m.get("matchday"),
                    "utc_date": m.get("utcDate"),
                    "status": m.get("status"),
                    "home_team_id": home.get("id"),
                    "home_team_name": home.get("shortName") or home.get("name"),
                    "away_team_id": away.get("id"),
                    "away_team_name": away.get("shortName") or away.get("name"),
                    "home_score": ft.get("home"),
                    "away_score": ft.get("away"),
                }
            )
        return out


def get_client_from_env() -> FootballDataOrgClient:
    key = os.getenv("FOOTBALL_DATA_API_KEY") or os.getenv("FOOTBALLDATA_API_KEY")
    if not key:
        raise RuntimeError("missing FOOTBALL_DATA_API_KEY")
    return FootballDataOrgClient(api_key=key)


DEFAULT_MAJOR_LEAGUES = ["PL", "PD", "SA", "BL1", "FL1"]


def fetch_major_league_matches(date_from: str, date_to: str, competitions: list[str] | None = None) -> list[dict[str, Any]]:
    client = get_client_from_env()
    rows: list[dict[str, Any]] = []
    for code in (competitions or DEFAULT_MAJOR_LEAGUES):
        rows.extend(client.fetch_matches(code, date_from, date_to))
    return rows

