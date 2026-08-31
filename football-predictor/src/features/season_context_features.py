from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from data.competition_registry import CompetitionRegistry, load_competition_registry
from data.transform_rules import parse_match_dates


SEASON_CONTEXT_FEATURE_COLUMNS = [
    "season_progress",
    "season_progress_available",
    "home_matches_played_before",
    "away_matches_played_before",
    "matches_played_diff",
    "season_early_flag",
    "season_mid_flag",
    "season_late_flag",
    "competition_known_flag",
    "competition_is_league",
    "competition_is_cup",
    "competition_is_national_team",
]


def _precomputed_or_zero(df: pd.DataFrame) -> pd.DataFrame:
    output = pd.DataFrame(index=df.index)
    for column in SEASON_CONTEXT_FEATURE_COLUMNS:
        source = df[column] if column in df.columns else pd.Series(0.0, index=df.index)
        output[column] = pd.to_numeric(source, errors="coerce").fillna(0.0).astype(float)
    return output


def _infer_season(match_date: pd.Timestamp, season_format: str) -> str:
    if season_format == "calendar_year":
        return str(int(match_date.year))
    if season_format == "tournament":
        return str(int(match_date.year))
    start_year = int(match_date.year if match_date.month >= 7 else match_date.year - 1)
    return f"{start_year:04d}-{(start_year + 1) % 100:02d}"


def _competition_label(row: pd.Series) -> object:
    for column in ("competition_id", "competition", "league"):
        value = row.get(column)
        if value is not None and not pd.isna(value) and str(value).strip():
            return value
    return ""


def _clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def build_season_context_features(
    df: pd.DataFrame,
    *,
    registry: CompetitionRegistry | None = None,
    date_col: str = "date",
    home_team_col: str = "home_team",
    away_team_col: str = "away_team",
    season_col: str = "season",
    early_threshold: float = 0.20,
    late_threshold: float = 0.75,
) -> pd.DataFrame:
    if set(SEASON_CONTEXT_FEATURE_COLUMNS) <= set(df.columns):
        return _precomputed_or_zero(df)
    required = {date_col, home_team_col, away_team_col}
    if not required <= set(df.columns):
        return _precomputed_or_zero(df)

    registry = registry or load_competition_registry()
    data = df.copy()
    data["_season_context_date"] = parse_match_dates(data[date_col])
    if data["_season_context_date"].isna().any():
        raise ValueError("date contains values that cannot be parsed for season context")
    data["_season_context_order"] = np.arange(len(data))
    data = data.sort_values(["_season_context_date", "_season_context_order"], kind="mergesort")

    played: defaultdict[tuple[str, str, str], int] = defaultdict(int)
    rows: dict[Any, dict[str, float]] = {}
    for match_date, matchday in data.groupby("_season_context_date", sort=True):
        pending: list[tuple[str, str, str]] = []
        for index, row in matchday.iterrows():
            raw_competition = _competition_label(row)
            definition = registry.resolve(raw_competition)
            metadata = registry.annotate(raw_competition)
            competition_id = str(metadata["competition_id"])
            season_format = str(metadata["season_format"])
            raw_season = row.get(season_col)
            season = (
                str(raw_season).strip()
                if raw_season is not None and not pd.isna(raw_season) and str(raw_season).strip()
                else _infer_season(match_date, season_format)
            )
            home = _clean_text(row.get(home_team_col))
            away = _clean_text(row.get(away_team_col))
            home_key = (competition_id, season, home)
            away_key = (competition_id, season, away)
            home_played = float(played[home_key])
            away_played = float(played[away_key])
            total_rounds = definition.total_rounds if definition is not None else None
            progress_available = float(bool(total_rounds and total_rounds > 0))
            progress = (
                float(np.clip(((home_played + away_played) / 2.0) / float(total_rounds), 0.0, 1.0))
                if progress_available
                else 0.0
            )
            competition_type = str(metadata["competition_type"])
            is_league = float(competition_type == "league")
            is_national = float(competition_type == "national_team_tournament")
            is_cup = float(competition_type in {"domestic_cup", "continental_cup"})
            rows[index] = {
                "season_progress": progress,
                "season_progress_available": progress_available,
                "home_matches_played_before": home_played,
                "away_matches_played_before": away_played,
                "matches_played_diff": home_played - away_played,
                "season_early_flag": float(progress_available and progress < float(early_threshold)),
                "season_mid_flag": float(
                    progress_available and float(early_threshold) <= progress < float(late_threshold)
                ),
                "season_late_flag": float(progress_available and progress >= float(late_threshold)),
                "competition_known_flag": float(bool(metadata["competition_known"])),
                "competition_is_league": is_league,
                "competition_is_cup": is_cup,
                "competition_is_national_team": is_national,
            }
            if home:
                pending.append(home_key)
            if away:
                pending.append(away_key)
        for key in pending:
            played[key] += 1

    output = pd.DataFrame.from_dict(rows, orient="index").reindex(df.index)
    return output[SEASON_CONTEXT_FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(0.0)
