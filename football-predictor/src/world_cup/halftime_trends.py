from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

from world_cup.data import normalize_national_team


RAW_ROOT = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"


def download_statsbomb_world_cup_events(
    cache_dir: str | Path,
    *,
    seasons: tuple[tuple[int, int], ...] = ((43, 3), (43, 106)),
    timeout: int = 90,
) -> dict[str, object]:
    root = Path(cache_dir)
    events_dir = root / "events"
    matches_dir = root / "matches"
    events_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    matches = 0
    for competition_id, season_id in seasons:
        matches_path = matches_dir / f"{competition_id}_{season_id}.json"
        if not matches_path.exists():
            raise FileNotFoundError(
                f"missing StatsBomb matches file: {matches_path}. Run import_statsbomb_world_cups first."
            )
        for match in json.loads(matches_path.read_text(encoding="utf-8")):
            matches += 1
            match_id = int(match["match_id"])
            destination = events_dir / f"{match_id}.json"
            if destination.exists():
                continue
            url = f"{RAW_ROOT}/events/{match_id}.json"
            last_error: Exception | None = None
            for attempt in range(5):
                try:
                    response = requests.get(url, timeout=timeout)
                    response.raise_for_status()
                    payload = response.content
                    json.loads(payload.decode("utf-8"))
                    temporary = destination.with_suffix(".json.part")
                    temporary.write_bytes(payload)
                    os.replace(temporary, destination)
                    downloaded += 1
                    break
                except Exception as exc:
                    last_error = exc
                    time.sleep(2**attempt)
            else:
                raise RuntimeError(f"failed to download {url}") from last_error
    return {
        "matches": matches,
        "event_files": len(list(events_dir.glob("*.json"))),
        "downloaded": downloaded,
        "source": "https://github.com/statsbomb/open-data",
    }


def _result_label(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "H"
    if home_goals < away_goals:
        return "A"
    return "D"


def _stage_bucket(stage: str) -> str:
    return "group" if stage == "Group Stage" else "knockout"


def _goal_team(event: dict[str, object]) -> str:
    event_type = (event.get("type") or {}).get("name")
    if event_type == "Shot":
        shot = event.get("shot") or {}
        if (shot.get("outcome") or {}).get("name") == "Goal":
            return str((event.get("team") or {}).get("name") or "")
    if event_type == "Own Goal For":
        return str((event.get("team") or {}).get("name") or "")
    return ""


def first_half_score_from_events(
    events: list[dict[str, object]],
    *,
    home_team: str,
    away_team: str,
) -> tuple[int, int]:
    home = normalize_national_team(home_team)
    away = normalize_national_team(away_team)
    home_goals = 0
    away_goals = 0
    for event in events:
        if int(event.get("period") or 0) != 1:
            continue
        team = normalize_national_team(_goal_team(event))
        if not team:
            continue
        if team == home:
            home_goals += 1
        elif team == away:
            away_goals += 1
    return home_goals, away_goals


def build_world_cup_halftime_match_rows(cache_dir: str | Path) -> pd.DataFrame:
    root = Path(cache_dir)
    rows: list[dict[str, object]] = []
    for matches_path in sorted((root / "matches").glob("43_*.json")):
        for match in json.loads(matches_path.read_text(encoding="utf-8")):
            match_id = int(match["match_id"])
            events_path = root / "events" / f"{match_id}.json"
            if not events_path.exists():
                continue
            home_team = normalize_national_team(match["home_team"]["home_team_name"])
            away_team = normalize_national_team(match["away_team"]["away_team_name"])
            events = json.loads(events_path.read_text(encoding="utf-8"))
            ht_home, ht_away = first_half_score_from_events(
                events,
                home_team=home_team,
                away_team=away_team,
            )
            ft_home = int(match["home_score"])
            ft_away = int(match["away_score"])
            stage = str(match.get("competition_stage", {}).get("name") or "")
            rows.append(
                {
                    "match_id": match_id,
                    "season": str(match["season"]["season_name"]),
                    "date": match["match_date"],
                    "stage": stage,
                    "stage_bucket": _stage_bucket(stage),
                    "home_team": home_team,
                    "away_team": away_team,
                    "half_time_home_goals": ht_home,
                    "half_time_away_goals": ht_away,
                    "full_time_home_goals_90": ft_home,
                    "full_time_away_goals_90": ft_away,
                    "half_time_total_goals": ht_home + ht_away,
                    "full_time_total_goals_90": ft_home + ft_away,
                    "second_half_goals": (ft_home + ft_away) - (ht_home + ht_away),
                    "half_time_result": _result_label(ht_home, ht_away),
                    "full_time_result_90": _result_label(ft_home, ft_away),
                    "half_full_result": f"{_result_label(ht_home, ht_away)}-{_result_label(ft_home, ft_away)}",
                    "over_0_5_ht": int(ht_home + ht_away >= 1),
                    "over_1_5_ht": int(ht_home + ht_away >= 2),
                    "over_1_5_ft": int(ft_home + ft_away >= 2),
                    "over_2_5_ft": int(ft_home + ft_away >= 3),
                    "over_3_5_ft": int(ft_home + ft_away >= 4),
                    "both_teams_scored": int(ft_home > 0 and ft_away > 0),
                }
            )
    return pd.DataFrame(rows).sort_values(["season", "date", "match_id"])


def summarize_halftime_trends(matches: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if matches.empty:
        empty = pd.DataFrame()
        return {
            "stage_summary": empty,
            "goal_distribution": empty,
            "half_full_distribution": empty,
            "season_stage_summary": empty,
        }

    def _summary(frame: pd.DataFrame) -> pd.Series:
        return pd.Series(
            {
                "matches": len(frame),
                "avg_ft_goals": frame["full_time_total_goals_90"].mean(),
                "avg_ht_goals": frame["half_time_total_goals"].mean(),
                "draw_ht_rate": frame["half_time_result"].eq("D").mean(),
                "draw_ft_rate": frame["full_time_result_90"].eq("D").mean(),
                "over_0_5_ht_rate": frame["over_0_5_ht"].mean(),
                "over_1_5_ht_rate": frame["over_1_5_ht"].mean(),
                "over_1_5_ft_rate": frame["over_1_5_ft"].mean(),
                "over_2_5_ft_rate": frame["over_2_5_ft"].mean(),
                "over_3_5_ft_rate": frame["over_3_5_ft"].mean(),
                "both_teams_scored_rate": frame["both_teams_scored"].mean(),
            }
        )

    stage_summary = (
        matches.groupby("stage_bucket", sort=False).apply(_summary, include_groups=False).reset_index()
    )
    season_stage_summary = (
        matches.groupby(["season", "stage_bucket"], sort=False)
        .apply(_summary, include_groups=False)
        .reset_index()
    )
    goal_distribution = (
        matches.groupby(["stage_bucket", "full_time_total_goals_90"])
        .size()
        .reset_index(name="matches")
    )
    goal_distribution["share"] = goal_distribution["matches"] / goal_distribution.groupby(
        "stage_bucket"
    )["matches"].transform("sum")
    half_full_distribution = (
        matches.groupby(["stage_bucket", "half_full_result"])
        .size()
        .reset_index(name="matches")
    )
    half_full_distribution["share"] = half_full_distribution["matches"] / half_full_distribution.groupby(
        "stage_bucket"
    )["matches"].transform("sum")
    return {
        "stage_summary": stage_summary,
        "goal_distribution": goal_distribution,
        "half_full_distribution": half_full_distribution,
        "season_stage_summary": season_stage_summary,
    }
