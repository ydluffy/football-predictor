from __future__ import annotations

from collections import defaultdict, deque

import numpy as np
import pandas as pd

from data.transform_rules import parse_match_dates


SCHEDULE_FEATURE_COLUMNS = [
    "home_rest_days",
    "away_rest_days",
    "rest_days_diff",
    "home_matches_7d",
    "away_matches_7d",
    "matches_7d_diff",
    "home_matches_14d",
    "away_matches_14d",
    "matches_14d_diff",
    "home_short_rest_flag",
    "away_short_rest_flag",
    "short_rest_diff",
    "home_schedule_seen",
    "away_schedule_seen",
]


def _precomputed_or_zero(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for col in SCHEDULE_FEATURE_COLUMNS:
        if col in df.columns:
            out[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
        else:
            out[col] = 0.0
    return out


def _matches_within(dates: deque[pd.Timestamp], current: pd.Timestamp, days: int) -> float:
    return float(sum(0 < (current - previous).days <= days for previous in dates))


def build_schedule_features(
    df: pd.DataFrame,
    *,
    external_calendar: pd.DataFrame | None = None,
    date_col: str = "date",
    home_team_col: str = "home_team",
    away_team_col: str = "away_team",
    default_rest_days: float = 14.0,
    max_rest_days: float = 30.0,
    short_rest_days: float = 3.0,
) -> pd.DataFrame:
    if set(SCHEDULE_FEATURE_COLUMNS) <= set(df.columns):
        return _precomputed_or_zero(df)

    required = {date_col, home_team_col, away_team_col}
    if not required <= set(df.columns):
        return _precomputed_or_zero(df)

    data = df.copy()
    data["_schedule_date"] = parse_match_dates(data[date_col])
    if data["_schedule_date"].isna().any():
        raise ValueError("date contains values that cannot be parsed for schedule features")

    data["_schedule_order"] = np.arange(len(data))
    data["_schedule_target"] = True
    data["_schedule_target_index"] = data.index
    if external_calendar is not None and not external_calendar.empty:
        external_required = {"date", "home_team", "away_team"}
        if not external_required <= set(external_calendar.columns):
            raise ValueError("external_calendar requires date, home_team, and away_team")
        external = external_calendar[["date", "home_team", "away_team"]].copy()
        external["_schedule_date"] = parse_match_dates(external["date"])
        if external["_schedule_date"].isna().any():
            raise ValueError("external_calendar contains unparseable dates")
        external["_schedule_order"] = np.arange(len(external)) + len(data)
        external["_schedule_target"] = False
        external["_schedule_target_index"] = pd.NA
        data = pd.concat([data, external], ignore_index=True, sort=False)
    data = data.sort_values(["_schedule_date", "_schedule_order"], kind="mergesort")
    team_dates: defaultdict[str, deque[pd.Timestamp]] = defaultdict(lambda: deque(maxlen=20))
    rows: dict[object, dict[str, float]] = {}

    for match_date, matchday in data.groupby("_schedule_date", sort=True):
        pending: list[str] = []
        for idx, row in matchday.iterrows():
            home = None if pd.isna(row[home_team_col]) else str(row[home_team_col])
            away = None if pd.isna(row[away_team_col]) else str(row[away_team_col])
            if not bool(row["_schedule_target"]):
                if home is not None:
                    pending.append(home)
                if away is not None:
                    pending.append(away)
                continue
            if home is None or away is None:
                continue
            home_dates = team_dates[home]
            away_dates = team_dates[away]

            home_seen = float(bool(home_dates))
            away_seen = float(bool(away_dates))
            home_rest = (
                min(float((match_date - home_dates[-1]).days), float(max_rest_days))
                if home_dates
                else float(default_rest_days)
            )
            away_rest = (
                min(float((match_date - away_dates[-1]).days), float(max_rest_days))
                if away_dates
                else float(default_rest_days)
            )
            home_7 = _matches_within(home_dates, match_date, 7)
            away_7 = _matches_within(away_dates, match_date, 7)
            home_14 = _matches_within(home_dates, match_date, 14)
            away_14 = _matches_within(away_dates, match_date, 14)
            home_short = float(home_seen > 0.0 and home_rest <= float(short_rest_days))
            away_short = float(away_seen > 0.0 and away_rest <= float(short_rest_days))

            target_index = row["_schedule_target_index"]
            rows[target_index] = {
                "home_rest_days": home_rest,
                "away_rest_days": away_rest,
                "rest_days_diff": home_rest - away_rest,
                "home_matches_7d": home_7,
                "away_matches_7d": away_7,
                "matches_7d_diff": home_7 - away_7,
                "home_matches_14d": home_14,
                "away_matches_14d": away_14,
                "matches_14d_diff": home_14 - away_14,
                "home_short_rest_flag": home_short,
                "away_short_rest_flag": away_short,
                "short_rest_diff": home_short - away_short,
                "home_schedule_seen": home_seen,
                "away_schedule_seen": away_seen,
            }
            pending.extend([home, away])

        for team in pending:
            team_dates[team].append(match_date)

    out = pd.DataFrame.from_dict(rows, orient="index").reindex(df.index)
    return out[SCHEDULE_FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(0.0)
