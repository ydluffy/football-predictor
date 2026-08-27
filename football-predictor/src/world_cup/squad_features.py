from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from world_cup.data import normalize_national_team
from world_cup.player_data import PlayerDataBundle


TEAM_SQUAD_FEATURE_COLUMNS = [
    "squad_players",
    "expected_starters",
    "starter_available_rate",
    "unavailable_players",
    "doubtful_players",
    "starter_minutes_30",
    "starter_minutes_90",
    "starter_goal_contributions_90",
    "starter_xg_xa_90",
    "starter_recent_load_14",
    "average_national_caps",
    "average_shared_starts",
    "previous_lineup_retention",
    "same_club_starter_pairs",
    "club_concentration",
]


def _latest_snapshot(
    squads: pd.DataFrame,
    *,
    team: str,
    as_of_date: pd.Timestamp,
) -> pd.DataFrame:
    eligible = squads[
        squads["team"].eq(team)
        & squads["snapshot_date"].le(as_of_date)
    ]
    if eligible.empty:
        raise ValueError(f"no squad snapshot for {team} on or before {as_of_date.date()}")
    latest = eligible["snapshot_date"].max()
    return eligible[eligible["snapshot_date"].eq(latest)].copy()


def _latest_availability(
    availability: pd.DataFrame,
    *,
    team: str,
    player_ids: set[str],
    as_of_date: pd.Timestamp,
) -> pd.DataFrame:
    eligible = availability[
        availability["team"].eq(team)
        & availability["player_id"].isin(player_ids)
        & availability["as_of_date"].le(as_of_date)
    ].sort_values("as_of_date", kind="mergesort")
    if eligible.empty:
        return pd.DataFrame(
            {
                "player_id": list(player_ids),
                "status": ["unknown"] * len(player_ids),
            }
        )
    latest = eligible.drop_duplicates("player_id", keep="last")[
        ["player_id", "status"]
    ]
    missing = player_ids - set(latest["player_id"])
    if missing:
        latest = pd.concat(
            [
                latest,
                pd.DataFrame(
                    {
                        "player_id": sorted(missing),
                        "status": ["unknown"] * len(missing),
                    }
                ),
            ],
            ignore_index=True,
        )
    return latest


def _recent_club_totals(
    appearances: pd.DataFrame,
    *,
    player_ids: set[str],
    as_of_date: pd.Timestamp,
    days: int,
) -> pd.DataFrame:
    start = as_of_date - pd.Timedelta(days=days)
    recent = appearances[
        appearances["player_id"].isin(player_ids)
        & appearances["match_date"].lt(as_of_date)
        & appearances["match_date"].ge(start)
    ]
    if recent.empty:
        return pd.DataFrame(index=pd.Index(sorted(player_ids), name="player_id"))
    return recent.groupby("player_id").agg(
        minutes=("minutes", "sum"),
        goals=("goals", "sum"),
        assists=("assists", "sum"),
        xg=("xg", "sum"),
        xa=("xa", "sum"),
    )


def _national_experience(
    appearances: pd.DataFrame,
    *,
    team: str,
    starter_ids: list[str],
    as_of_date: pd.Timestamp,
) -> tuple[float, float, float]:
    history = appearances[
        appearances["team"].eq(team)
        & appearances["match_date"].lt(as_of_date)
    ].copy()
    if not starter_ids or history.empty:
        return 0.0, 0.0, 0.0

    caps = history.groupby("player_id").size()
    average_caps = float(np.mean([caps.get(player_id, 0) for player_id in starter_ids]))

    started = history[history["started"]]
    match_keys = ["match_date", "team", "opponent"]
    pair_counts: dict[tuple[str, str], int] = {}
    for _, lineup in started.groupby(match_keys, sort=False):
        players = sorted(set(lineup["player_id"]) & set(starter_ids))
        for first, second in combinations(players, 2):
            pair_counts[(first, second)] = pair_counts.get((first, second), 0) + 1
    starter_pairs = list(combinations(sorted(starter_ids), 2))
    average_shared = (
        float(np.mean([pair_counts.get(pair, 0) for pair in starter_pairs]))
        if starter_pairs
        else 0.0
    )

    previous_retention = 0.0
    if not started.empty:
        last_date = started["match_date"].max()
        previous_lineup = set(started[started["match_date"].eq(last_date)]["player_id"])
        previous_retention = len(previous_lineup & set(starter_ids)) / len(starter_ids)
    return average_caps, average_shared, float(previous_retention)


def build_team_squad_features(
    bundle: PlayerDataBundle,
    *,
    team: str,
    as_of_date: str | pd.Timestamp,
) -> dict[str, float]:
    team_name = normalize_national_team(team)
    cutoff = pd.Timestamp(as_of_date).normalize()
    squad = _latest_snapshot(bundle.squads, team=team_name, as_of_date=cutoff)
    player_ids = set(squad["player_id"])
    availability = _latest_availability(
        bundle.availability,
        team=team_name,
        player_ids=player_ids,
        as_of_date=cutoff,
    )
    squad = squad.merge(availability, on="player_id", how="left", validate="one_to_one")
    starters = squad[squad["role"].eq("starter")].copy()
    starter_ids = starters["player_id"].tolist()
    starter_set = set(starter_ids)

    club_30 = _recent_club_totals(
        bundle.club_appearances,
        player_ids=starter_set,
        as_of_date=cutoff,
        days=30,
    )
    club_90 = _recent_club_totals(
        bundle.club_appearances,
        player_ids=starter_set,
        as_of_date=cutoff,
        days=90,
    )
    club_14 = _recent_club_totals(
        bundle.club_appearances,
        player_ids=starter_set,
        as_of_date=cutoff,
        days=14,
    )
    minutes_90 = float(club_90.get("minutes", pd.Series(dtype=float)).sum())
    goal_contributions = float(
        club_90.get("goals", pd.Series(dtype=float)).sum()
        + club_90.get("assists", pd.Series(dtype=float)).sum()
    )
    xg_xa = float(
        club_90.get("xg", pd.Series(dtype=float)).sum()
        + club_90.get("xa", pd.Series(dtype=float)).sum()
    )
    denominator = max(minutes_90, 1.0)

    average_caps, average_shared, previous_retention = _national_experience(
        bundle.national_appearances,
        team=team_name,
        starter_ids=starter_ids,
        as_of_date=cutoff,
    )
    known_clubs = starters["club"].fillna("").astype(str).str.strip()
    known_clubs = known_clubs[known_clubs.ne("")]
    club_counts = known_clubs.value_counts()
    same_club_pairs = int(sum(count * (count - 1) // 2 for count in club_counts))
    starter_count = len(starters)
    club_concentration = (
        float((club_counts / starter_count).pow(2).sum())
        if starter_count
        else 0.0
    )
    unavailable_statuses = {"injured", "suspended", "unavailable"}
    starter_available = starters["status"].eq("available").sum()
    starter_known = starters["status"].ne("unknown").sum()

    return {
        "squad_players": float(len(squad)),
        "expected_starters": float(starter_count),
        "starter_available_rate": (
            float(starter_available / starter_known) if starter_known else 0.0
        ),
        "unavailable_players": float(squad["status"].isin(unavailable_statuses).sum()),
        "doubtful_players": float(squad["status"].eq("doubtful").sum()),
        "starter_minutes_30": float(
            club_30.get("minutes", pd.Series(dtype=float)).sum()
        ),
        "starter_minutes_90": minutes_90,
        "starter_goal_contributions_90": 90.0 * goal_contributions / denominator,
        "starter_xg_xa_90": 90.0 * xg_xa / denominator,
        "starter_recent_load_14": float(
            club_14.get("minutes", pd.Series(dtype=float)).sum()
        ),
        "average_national_caps": average_caps,
        "average_shared_starts": average_shared,
        "previous_lineup_retention": previous_retention,
        "same_club_starter_pairs": float(same_club_pairs),
        "club_concentration": club_concentration,
    }


def build_fixture_squad_features(
    bundle: PlayerDataBundle,
    fixtures: pd.DataFrame,
    *,
    date_col: str = "date",
    home_team_col: str = "home_team",
    away_team_col: str = "away_team",
) -> pd.DataFrame:
    rows = []
    for fixture in fixtures.itertuples(index=False):
        cutoff = pd.Timestamp(getattr(fixture, date_col))
        home = build_team_squad_features(
            bundle,
            team=getattr(fixture, home_team_col),
            as_of_date=cutoff,
        )
        away = build_team_squad_features(
            bundle,
            team=getattr(fixture, away_team_col),
            as_of_date=cutoff,
        )
        row: dict[str, float] = {}
        for column in TEAM_SQUAD_FEATURE_COLUMNS:
            row[f"home_{column}"] = home[column]
            row[f"away_{column}"] = away[column]
            row[f"{column}_diff"] = home[column] - away[column]
        rows.append(row)
    return pd.DataFrame(rows, index=fixtures.index)
