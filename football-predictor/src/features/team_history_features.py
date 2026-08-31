from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from data.transform_rules import parse_match_dates


HISTORY_FEATURE_COLUMNS = [
    "elo_home",
    "elo_away",
    "elo_diff",
    "home_form_points_5",
    "away_form_points_5",
    "form_points_diff_5",
    "home_goals_for_5",
    "away_goals_for_5",
    "goals_for_diff_5",
    "home_goals_against_5",
    "away_goals_against_5",
    "goals_against_diff_5",
    "home_home_points_5",
    "away_away_points_5",
    "venue_form_diff_5",
    "home_matches_seen",
    "away_matches_seen",
]

MODEL_HISTORY_FEATURE_COLUMNS = [
    "goals_for_diff_5",
    "goals_against_diff_5",
]

MATCH_STATS_HISTORY_FEATURE_COLUMNS = [
    "shots_on_target_diff_5",
    "shots_diff_5",
    "corners_diff_5",
    "net_shots_on_target_diff_5",
    "net_shots_diff_5",
    "net_corners_diff_5",
    "cards_diff_5",
    "home_match_stats_seen_5",
    "away_match_stats_seen_5",
]


@dataclass
class _TeamState:
    elo: float = 1500.0
    matches_seen: int = 0
    points: deque[float] = field(default_factory=lambda: deque(maxlen=5))
    goals_for: deque[float] = field(default_factory=lambda: deque(maxlen=5))
    goals_against: deque[float] = field(default_factory=lambda: deque(maxlen=5))
    home_points: deque[float] = field(default_factory=lambda: deque(maxlen=5))
    away_points: deque[float] = field(default_factory=lambda: deque(maxlen=5))
    shots_for: deque[float] = field(default_factory=lambda: deque(maxlen=5))
    shots_against: deque[float] = field(default_factory=lambda: deque(maxlen=5))
    shots_on_target_for: deque[float] = field(default_factory=lambda: deque(maxlen=5))
    shots_on_target_against: deque[float] = field(default_factory=lambda: deque(maxlen=5))
    corners_for: deque[float] = field(default_factory=lambda: deque(maxlen=5))
    corners_against: deque[float] = field(default_factory=lambda: deque(maxlen=5))
    cards: deque[float] = field(default_factory=lambda: deque(maxlen=5))
    match_stats_seen: int = 0


def _mean(values: deque[float]) -> float:
    return float(np.mean(values)) if values else 0.0


def _precomputed_or_zero(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for col in HISTORY_FEATURE_COLUMNS + MATCH_STATS_HISTORY_FEATURE_COLUMNS:
        if col in df.columns:
            out[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
        else:
            out[col] = 0.0
    return out


def _optional_number(row: pd.Series, name: str) -> float | None:
    if name not in row.index or pd.isna(row[name]):
        return None
    return float(row[name])


def build_team_history_features(
    df: pd.DataFrame,
    *,
    date_col: str = "date",
    home_team_col: str = "home_team",
    away_team_col: str = "away_team",
    home_goals_col: str = "home_goals",
    away_goals_col: str = "away_goals",
    result_col: str = "actual_result",
    k_factor: float = 20.0,
    home_advantage: float = 65.0,
) -> pd.DataFrame:
    all_feature_columns = HISTORY_FEATURE_COLUMNS + MATCH_STATS_HISTORY_FEATURE_COLUMNS
    if set(all_feature_columns) <= set(df.columns):
        return _precomputed_or_zero(df)

    required_context = {date_col, home_team_col, away_team_col}
    if not required_context <= set(df.columns):
        return _precomputed_or_zero(df)

    has_scores = {home_goals_col, away_goals_col} <= set(df.columns)
    if not has_scores and result_col not in df.columns:
        return _precomputed_or_zero(df)

    data = df.copy()
    data["_history_date"] = parse_match_dates(data[date_col])
    if data["_history_date"].isna().any():
        raise ValueError("date 存在无法解析的值，无法构造球队历史特征")

    data["_history_order"] = np.arange(len(data))
    data = data.sort_values(["_history_date", "_history_order"], kind="mergesort")
    states: defaultdict[str, _TeamState] = defaultdict(_TeamState)
    rows: dict[object, dict[str, float]] = {}

    for _, matchday in data.groupby("_history_date", sort=True):
        pending_updates: list[dict[str, object]] = []

        for idx, row in matchday.iterrows():
            home = str(row[home_team_col])
            away = str(row[away_team_col])
            hs = states[home]
            aws = states[away]

            rows[idx] = {
                "elo_home": hs.elo / 400.0,
                "elo_away": aws.elo / 400.0,
                "elo_diff": (hs.elo + float(home_advantage) - aws.elo) / 400.0,
                "home_form_points_5": _mean(hs.points),
                "away_form_points_5": _mean(aws.points),
                "form_points_diff_5": _mean(hs.points) - _mean(aws.points),
                "home_goals_for_5": _mean(hs.goals_for),
                "away_goals_for_5": _mean(aws.goals_for),
                "goals_for_diff_5": _mean(hs.goals_for) - _mean(aws.goals_for),
                "home_goals_against_5": _mean(hs.goals_against),
                "away_goals_against_5": _mean(aws.goals_against),
                "goals_against_diff_5": _mean(hs.goals_against) - _mean(aws.goals_against),
                "home_home_points_5": _mean(hs.home_points),
                "away_away_points_5": _mean(aws.away_points),
                "venue_form_diff_5": _mean(hs.home_points) - _mean(aws.away_points),
                "home_matches_seen": float(hs.matches_seen),
                "away_matches_seen": float(aws.matches_seen),
                "shots_on_target_diff_5": _mean(hs.shots_on_target_for) - _mean(aws.shots_on_target_for),
                "shots_diff_5": _mean(hs.shots_for) - _mean(aws.shots_for),
                "corners_diff_5": _mean(hs.corners_for) - _mean(aws.corners_for),
                "net_shots_on_target_diff_5": (
                    _mean(hs.shots_on_target_for)
                    - _mean(hs.shots_on_target_against)
                    - _mean(aws.shots_on_target_for)
                    + _mean(aws.shots_on_target_against)
                ),
                "net_shots_diff_5": (
                    _mean(hs.shots_for)
                    - _mean(hs.shots_against)
                    - _mean(aws.shots_for)
                    + _mean(aws.shots_against)
                ),
                "net_corners_diff_5": (
                    _mean(hs.corners_for)
                    - _mean(hs.corners_against)
                    - _mean(aws.corners_for)
                    + _mean(aws.corners_against)
                ),
                "cards_diff_5": _mean(hs.cards) - _mean(aws.cards),
                "home_match_stats_seen_5": float(min(hs.match_stats_seen, 5)),
                "away_match_stats_seen_5": float(min(aws.match_stats_seen, 5)),
            }

            result = str(row.get(result_col, "")).upper()
            if has_scores:
                home_goals = float(row[home_goals_col])
                away_goals = float(row[away_goals_col])
                result = "H" if home_goals > away_goals else "A" if home_goals < away_goals else "D"
            else:
                home_goals = 0.0
                away_goals = 0.0
            pending_updates.append(
                {
                    "home": home,
                    "away": away,
                    "home_goals": home_goals,
                    "away_goals": away_goals,
                    "result": result,
                    "home_shots": _optional_number(row, "home_shots"),
                    "away_shots": _optional_number(row, "away_shots"),
                    "home_shots_on_target": _optional_number(row, "home_shots_on_target"),
                    "away_shots_on_target": _optional_number(row, "away_shots_on_target"),
                    "home_corners": _optional_number(row, "home_corners"),
                    "away_corners": _optional_number(row, "away_corners"),
                    "home_cards": (
                        (_optional_number(row, "home_yellow_cards") or 0.0)
                        + 2.0 * (_optional_number(row, "home_red_cards") or 0.0)
                    ),
                    "away_cards": (
                        (_optional_number(row, "away_yellow_cards") or 0.0)
                        + 2.0 * (_optional_number(row, "away_red_cards") or 0.0)
                    ),
                }
            )

        for update in pending_updates:
            home = str(update["home"])
            away = str(update["away"])
            home_goals = float(update["home_goals"])
            away_goals = float(update["away_goals"])
            result = str(update["result"])
            hs = states[home]
            aws = states[away]
            home_score = 1.0 if result == "H" else 0.5 if result == "D" else 0.0
            expected_home = 1.0 / (
                1.0 + 10.0 ** (-(hs.elo + float(home_advantage) - aws.elo) / 400.0)
            )
            delta = float(k_factor) * (home_score - expected_home)
            hs.elo += delta
            aws.elo -= delta

            home_points = 3.0 if result == "H" else 1.0 if result == "D" else 0.0
            away_points = 3.0 if result == "A" else 1.0 if result == "D" else 0.0
            hs.points.append(home_points)
            aws.points.append(away_points)
            hs.home_points.append(home_points)
            aws.away_points.append(away_points)
            hs.goals_for.append(home_goals)
            hs.goals_against.append(away_goals)
            aws.goals_for.append(away_goals)
            aws.goals_against.append(home_goals)
            hs.matches_seen += 1
            aws.matches_seen += 1

            if update["home_shots_on_target"] is not None and update["away_shots_on_target"] is not None:
                hs.shots_on_target_for.append(float(update["home_shots_on_target"]))
                hs.shots_on_target_against.append(float(update["away_shots_on_target"]))
                aws.shots_on_target_for.append(float(update["away_shots_on_target"]))
                aws.shots_on_target_against.append(float(update["home_shots_on_target"]))
                hs.match_stats_seen += 1
                aws.match_stats_seen += 1
            if update["home_shots"] is not None and update["away_shots"] is not None:
                hs.shots_for.append(float(update["home_shots"]))
                hs.shots_against.append(float(update["away_shots"]))
                aws.shots_for.append(float(update["away_shots"]))
                aws.shots_against.append(float(update["home_shots"]))
            if update["home_corners"] is not None and update["away_corners"] is not None:
                hs.corners_for.append(float(update["home_corners"]))
                hs.corners_against.append(float(update["away_corners"]))
                aws.corners_for.append(float(update["away_corners"]))
                aws.corners_against.append(float(update["home_corners"]))
            hs.cards.append(float(update["home_cards"]))
            aws.cards.append(float(update["away_cards"]))

    out = pd.DataFrame.from_dict(rows, orient="index")
    out = out.reindex(df.index)
    columns = HISTORY_FEATURE_COLUMNS + MATCH_STATS_HISTORY_FEATURE_COLUMNS
    return out[columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
