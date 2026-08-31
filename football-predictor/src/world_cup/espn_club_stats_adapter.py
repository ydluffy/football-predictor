from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"


def _download_json(url: str, destination: Path, *, timeout: int = 60) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, destination)
            return payload
        except Exception as exc:
            last_error = exc
            temporary.unlink(missing_ok=True)
            time.sleep(2**attempt)
    raise RuntimeError(f"failed to download {url}") from last_error


def _flatten_stats(athlete: dict) -> dict[str, float]:
    stats: dict[str, float] = {}
    splits = ((athlete.get("statistics") or {}).get("splits") or {})
    for category in splits.get("categories") or []:
        for stat in category.get("stats") or []:
            name = stat.get("name")
            if name:
                stats[str(name)] = float(stat.get("value") or 0.0)
    return stats


def parse_club_roster_stats(payload: dict, *, club_id: str, league_slug: str) -> list[dict]:
    team = payload.get("team") or {}
    season = payload.get("season") or {}
    rows = []
    for athlete in payload.get("athletes") or []:
        if not athlete.get("id"):
            continue
        stats = _flatten_stats(athlete)
        rows.append(
            {
                "source": "espn_public",
                "source_player_id": str(athlete["id"]),
                "player_id": f"espn_{athlete['id']}",
                "player_name": athlete.get("displayName") or athlete.get("fullName"),
                "club_id": club_id,
                "club": team.get("displayName") or "",
                "league_slug": league_slug,
                "season": season.get("displayName") or str(season.get("year") or ""),
                "appearances": stats.get("appearances", 0.0),
                "starts_proxy": max(
                    stats.get("appearances", 0.0) - stats.get("subIns", 0.0),
                    0.0,
                ),
                "goals": stats.get("totalGoals", 0.0),
                "assists": stats.get("goalAssists", 0.0),
                "shots": stats.get("totalShots", 0.0),
                "shots_on_target": stats.get("shotsOnTarget", 0.0),
                "saves": stats.get("saves", 0.0),
                "goals_conceded": stats.get("goalsConceded", 0.0),
                "yellow_cards": stats.get("yellowCards", 0.0),
                "red_cards": stats.get("redCards", 0.0),
            }
        )
    return rows


def import_espn_club_season_stats(
    *,
    player_data_dir: str | Path,
    cache_dir: str | Path,
    download: bool = True,
    limit_clubs: int | None = None,
) -> dict[str, object]:
    root = Path(player_data_dir)
    cache = Path(cache_dir)
    affiliations = pd.read_csv(root / "club_affiliations.csv")
    affiliations = affiliations[
        affiliations["club_id"].fillna("").astype(str).str.strip().ne("")
    ].copy()
    club_parts = affiliations["club_id"].astype(str).str.split(":", n=1, expand=True)
    affiliations["league_slug"] = club_parts[0]
    affiliations["team_id"] = club_parts[1]
    clubs = affiliations[["league_slug", "team_id", "club_id"]].drop_duplicates()
    if limit_clubs is not None:
        clubs = clubs.head(limit_clubs)

    rows = []
    source_rows = []
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for club in clubs.itertuples(index=False):
        url = f"{BASE_URL}/{club.league_slug}/teams/{club.team_id}/roster"
        path = cache / "club_rosters" / str(club.league_slug) / f"{club.team_id}.json"
        payload = (
            _download_json(url, path)
            if download
            else json.loads(path.read_text(encoding="utf-8"))
        )
        rows.extend(
            parse_club_roster_stats(
                payload,
                club_id=str(club.club_id),
                league_slug=str(club.league_slug),
            )
        )
        source_rows.append(
            {
                "source_type": "club_roster_stats",
                "source_url": url,
                "fetched_at": fetched_at,
                "record_id": club.club_id,
            }
        )

    stats = pd.DataFrame(rows).drop_duplicates(
        ["source", "source_player_id", "club_id"],
        keep="last",
    )
    stats = stats[stats["player_id"].isin(set(pd.read_csv(root / "players.csv")["player_id"]))]
    stats.to_csv(root / "club_season_stats.csv", index=False)
    source_path = root / "source_snapshots.csv"
    sources = pd.read_csv(source_path) if source_path.exists() else pd.DataFrame()
    pd.concat([sources, pd.DataFrame(source_rows)], ignore_index=True).to_csv(
        source_path,
        index=False,
    )
    players = pd.read_csv(root / "players.csv")
    covered = set(stats["player_id"]) if not stats.empty else set()
    return {
        "clubs_requested": int(len(clubs)),
        "club_season_stat_rows": int(len(stats)),
        "club_season_stat_player_coverage": (
            len(covered & set(players["player_id"])) / len(players) if len(players) else 0.0
        ),
        "download": bool(download),
        "output": str(root / "club_season_stats.csv"),
    }
