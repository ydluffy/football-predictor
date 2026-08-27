from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from world_cup.data import normalize_national_team
from world_cup.markets import implied_probabilities_from_decimal_odds


THE_ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"
SOURCE = "the_odds_api"

OddsIndex = dict[tuple[str, str], list[dict[str, Any]]]


class TheOddsApiClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = THE_ODDS_API_BASE_URL,
        timeout: int = 60,
    ) -> None:
        # ``None`` means "use the process environment"; an explicit empty
        # string deliberately disables the client.  This prevents a dry run
        # from silently picking up a real key from .env/process state.
        self.api_key = (
            os.getenv("THE_ODDS_API_KEY", "")
            if api_key is None
            else str(api_key).strip()
        )
        self.base_url = base_url.rstrip("/")
        self.timeout = int(timeout)
        self.last_headers: dict[str, str] = {}

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        if not self.api_key:
            raise RuntimeError("THE_ODDS_API_KEY is not configured")
        request_params = dict(params or {})
        request_params["apiKey"] = self.api_key
        response = requests.get(
            f"{self.base_url}/{endpoint.lstrip('/')}",
            params=request_params,
            timeout=self.timeout,
        )
        self.last_headers = dict(response.headers)
        response.raise_for_status()
        return response.json()


def fetch_odds(
    client: TheOddsApiClient,
    *,
    sport_key: str = "soccer_fifa_world_cup",
    regions: str = "eu,uk,us,au",
    markets: str = "h2h,spreads,totals",
    odds_format: str = "decimal",
    date_format: str = "iso",
    bookmakers: str = "",
) -> list[dict[str, Any]]:
    params = {
        "regions": regions,
        "markets": markets,
        "oddsFormat": odds_format,
        "dateFormat": date_format,
    }
    if bookmakers:
        params["bookmakers"] = bookmakers
    payload = client.get(f"sports/{sport_key}/odds", params=params)
    return payload if isinstance(payload, list) else []


def _outcome_label(
    *,
    outcome_name: str,
    market_key: str,
    home_team: str,
    away_team: str,
) -> str:
    normalized = outcome_name.strip().casefold()
    if market_key == "h2h":
        if normalized == home_team.strip().casefold():
            return "home"
        if normalized == away_team.strip().casefold():
            return "away"
        if normalized == "draw":
            return "draw"
    if market_key == "totals":
        if normalized == "over":
            return "over"
        if normalized == "under":
            return "under"
    if market_key == "spreads":
        if normalized == home_team.strip().casefold():
            return "home_spread"
        if normalized == away_team.strip().casefold():
            return "away_spread"
    return normalized.replace(" ", "_")


def odds_payload_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    out: list[dict[str, Any]] = []
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for event in rows:
        event_id = str(event.get("id", "")).strip()
        home_team_raw = str(event.get("home_team", "")).strip()
        away_team_raw = str(event.get("away_team", "")).strip()
        home_team = normalize_national_team(home_team_raw)
        away_team = normalize_national_team(away_team_raw)
        if not event_id or not home_team or not away_team:
            continue
        for bookmaker in event.get("bookmakers") or []:
            bookmaker_key = str(bookmaker.get("key", "")).strip()
            bookmaker_title = str(bookmaker.get("title", "")).strip()
            for market in bookmaker.get("markets") or []:
                market_key = str(market.get("key", "")).strip()
                for outcome in market.get("outcomes") or []:
                    outcome_name = str(outcome.get("name", "")).strip()
                    try:
                        price = float(outcome.get("price"))
                    except (TypeError, ValueError):
                        continue
                    point = outcome.get("point", "")
                    out.append(
                        {
                            "event_id": event_id,
                            "sport_key": event.get("sport_key", ""),
                            "sport_title": event.get("sport_title", ""),
                            "commence_time": event.get("commence_time", ""),
                            "date": str(event.get("commence_time", ""))[:10],
                            "home_team": home_team,
                            "away_team": away_team,
                            "raw_home_team": home_team_raw,
                            "raw_away_team": away_team_raw,
                            "bookmaker_key": bookmaker_key,
                            "bookmaker_title": bookmaker_title,
                            "bookmaker_last_update": bookmaker.get("last_update", ""),
                            "market_key": market_key,
                            "market_last_update": market.get("last_update", ""),
                            "outcome_name": outcome_name,
                            "outcome_label": _outcome_label(
                                outcome_name=outcome_name,
                                market_key=market_key,
                                home_team=home_team_raw,
                                away_team=away_team_raw,
                            ),
                            "price": price,
                            "point": point,
                            "source": SOURCE,
                            "fetched_at": fetched_at,
                        }
                    )
    return pd.DataFrame(
        out,
        columns=[
            "event_id",
            "sport_key",
            "sport_title",
            "commence_time",
            "date",
            "home_team",
            "away_team",
            "raw_home_team",
            "raw_away_team",
            "bookmaker_key",
            "bookmaker_title",
            "bookmaker_last_update",
            "market_key",
            "market_last_update",
            "outcome_name",
            "outcome_label",
            "price",
            "point",
            "source",
            "fetched_at",
        ],
    )


def summarize_odds_frame(odds: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "event_id",
        "date",
        "commence_time",
        "home_team",
        "away_team",
        "market_key",
        "point",
        "bookmaker_count",
        "outcome_count",
        "home_avg_odds",
        "draw_avg_odds",
        "away_avg_odds",
        "home_best_odds",
        "draw_best_odds",
        "away_best_odds",
        "home_market_probability",
        "draw_market_probability",
        "away_market_probability",
        "over_avg_odds",
        "under_avg_odds",
        "over_best_odds",
        "under_best_odds",
        "home_spread_avg_odds",
        "away_spread_avg_odds",
        "home_spread_best_odds",
        "away_spread_best_odds",
        "source",
        "fetched_at",
    ]
    if odds.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    grouped = odds.groupby(["event_id", "market_key", "point"], dropna=False)
    for (event_id, market_key, point), group in grouped:
        first = group.iloc[0]
        item: dict[str, Any] = {
            "event_id": event_id,
            "date": first.get("date", ""),
            "commence_time": first.get("commence_time", ""),
            "home_team": first.get("home_team", ""),
            "away_team": first.get("away_team", ""),
            "market_key": market_key,
            "point": point,
            "bookmaker_count": int(group["bookmaker_key"].nunique()),
            "outcome_count": int(len(group)),
            "source": SOURCE,
            "fetched_at": first.get("fetched_at", ""),
        }
        for label, prefix in (
            ("home", "home"),
            ("draw", "draw"),
            ("away", "away"),
            ("over", "over"),
            ("under", "under"),
            ("home_spread", "home_spread"),
            ("away_spread", "away_spread"),
        ):
            prices = pd.to_numeric(group.loc[group["outcome_label"].eq(label), "price"], errors="coerce").dropna()
            if prices.empty:
                continue
            item[f"{prefix}_avg_odds"] = float(prices.mean())
            item[f"{prefix}_best_odds"] = float(prices.max())

        if market_key == "h2h":
            probabilities = implied_probabilities_from_decimal_odds(
                {
                    "home": item.get("home_avg_odds"),
                    "draw": item.get("draw_avg_odds"),
                    "away": item.get("away_avg_odds"),
                }
            )
            item["home_market_probability"] = probabilities.get("home")
            item["draw_market_probability"] = probabilities.get("draw")
            item["away_market_probability"] = probabilities.get("away")
        rows.append(item)
    return pd.DataFrame(rows, columns=columns)


def load_the_odds_api_summary(path: str | Path | None) -> pd.DataFrame:
    if path is None:
        return summarize_odds_frame(pd.DataFrame())
    file_path = Path(path)
    if not file_path.exists():
        return summarize_odds_frame(pd.DataFrame())
    return pd.read_csv(file_path)


def index_the_odds_api_h2h(summary: pd.DataFrame) -> OddsIndex:
    if summary.empty:
        return {}
    required = {"home_team", "away_team", "market_key"}
    if not required.issubset(summary.columns):
        return {}
    h2h = summary[summary["market_key"].astype(str).eq("h2h")].copy()
    index: OddsIndex = {}
    for _, row in h2h.iterrows():
        key = (
            normalize_national_team(row.get("home_team", "")),
            normalize_national_team(row.get("away_team", "")),
        )
        if not key[0] or not key[1]:
            continue
        index.setdefault(key, []).append(row.to_dict())
    return index


def find_the_odds_api_h2h(
    index: OddsIndex,
    *,
    home_team: str,
    away_team: str,
    date: object | None = None,
) -> dict[str, Any]:
    key = (normalize_national_team(home_team), normalize_national_team(away_team))
    candidates = index.get(key, [])
    if not candidates:
        return {}
    if date is not None:
        target_date = str(pd.Timestamp(date).date())
        same_date = [row for row in candidates if str(row.get("date", "")) == target_date]
        if same_date:
            return same_date[0]
    return candidates[0]


def import_the_odds_api_world_cup(
    *,
    output_dir: str | Path,
    api_key: str | None = None,
    sport_key: str = "soccer_fifa_world_cup",
    regions: str = "eu,uk,us,au",
    markets: str = "h2h,spreads,totals",
    bookmakers: str = "",
    timeout: int = 60,
) -> dict[str, Any]:
    client = TheOddsApiClient(api_key=api_key, timeout=timeout)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    if not client.configured:
        odds_payload_to_frame([]).to_csv(output / "odds.csv", index=False)
        summarize_odds_frame(pd.DataFrame()).to_csv(output / "match_market_summary.csv", index=False)
        return {
            "source": SOURCE,
            "configured": False,
            "status": "skipped",
            "reason": "THE_ODDS_API_KEY is not configured",
            "output_dir": str(output),
        }

    payload = fetch_odds(
        client,
        sport_key=sport_key,
        regions=regions,
        markets=markets,
        bookmakers=bookmakers,
    )
    odds = odds_payload_to_frame(payload)
    summary = summarize_odds_frame(odds)
    odds.to_csv(output / "odds.csv", index=False)
    summary.to_csv(output / "match_market_summary.csv", index=False)

    return {
        "source": SOURCE,
        "configured": True,
        "status": "ok",
        "sport_key": sport_key,
        "regions": regions,
        "markets": markets,
        "bookmakers": bookmakers,
        "events": int(len(payload)),
        "odds_rows": int(len(odds)),
        "summary_rows": int(len(summary)),
        "bookmakers": sorted(odds["bookmaker_key"].dropna().unique().tolist()) if not odds.empty else [],
        "requests_remaining": client.last_headers.get("x-requests-remaining", ""),
        "requests_used": client.last_headers.get("x-requests-used", ""),
        "output_dir": str(output),
    }
