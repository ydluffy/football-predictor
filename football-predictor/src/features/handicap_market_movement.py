from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


OUTPUT_COLUMNS = [
    "match_id",
    "source_fixture_id",
    "competition_id",
    "home_team",
    "away_team",
    "kickoff_at",
    "snapshot_count",
    "bookmaker_count",
    "opening_captured_at",
    "latest_captured_at",
    "movement_hours",
    "opening_home_handicap_median",
    "latest_home_handicap_median",
    "home_line_strength_delta",
    "opening_home_price_probability_median",
    "latest_home_price_probability_median",
    "home_price_probability_delta",
    "line_strength_per_hour",
    "favorite_hot_without_line_support",
    "line_upgrade_without_price_support",
    "line_downgrade",
    "safe_for_shadow_features",
]


def _truthy(value: object) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def _two_way_no_vig(home_odds: pd.Series, away_odds: pd.Series) -> pd.Series:
    home = pd.to_numeric(home_odds, errors="coerce")
    away = pd.to_numeric(away_odds, errors="coerce")
    home_inverse = 1.0 / home.where(home > 1.0)
    away_inverse = 1.0 / away.where(away > 1.0)
    return home_inverse / (home_inverse + away_inverse)


def build_api_football_handicap_movement(
    history: pd.DataFrame,
    *,
    as_of: object | None = None,
) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    required = {
        "match_id", "snapshot_id", "captured_at", "source_fixture_id", "competition_id",
        "home_team", "away_team", "kickoff_at", "bookmaker_id", "home_handicap",
        "home_odds", "away_odds", "mapping_status", "before_kickoff",
        "eligible_for_primary_research",
    }
    missing = required - set(history.columns)
    if missing:
        raise ValueError(f"missing API-Football movement columns: {sorted(missing)}")

    frame = history.copy()
    frame = frame[
        frame["mapping_status"].astype(str).eq("mapped")
        & frame["before_kickoff"].map(_truthy)
        & frame["eligible_for_primary_research"].map(_truthy)
        & frame["match_id"].astype(str).str.strip().ne("")
    ].copy()
    frame["captured_parsed"] = pd.to_datetime(
        frame["captured_at"], errors="coerce", utc=True, format="mixed"
    )
    frame["kickoff_parsed"] = pd.to_datetime(
        frame["kickoff_at"], errors="coerce", utc=True, format="mixed"
    )
    if as_of is not None:
        cutoff = pd.to_datetime(as_of, errors="coerce", utc=True)
        frame = frame[frame["captured_parsed"].le(cutoff)]
    frame = frame[
        frame["captured_parsed"].notna()
        & frame["kickoff_parsed"].notna()
        & frame["captured_parsed"].lt(frame["kickoff_parsed"])
    ].copy()
    frame["home_handicap_numeric"] = pd.to_numeric(frame["home_handicap"], errors="coerce")
    frame["home_price_probability"] = _two_way_no_vig(frame["home_odds"], frame["away_odds"])
    frame = frame[frame["home_handicap_numeric"].notna() & frame["home_price_probability"].notna()]
    if frame.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    snapshots = (
        frame.groupby(["match_id", "snapshot_id"], sort=False)
        .agg(
            captured_at=("captured_parsed", "max"),
            source_fixture_id=("source_fixture_id", "first"),
            competition_id=("competition_id", "first"),
            home_team=("home_team", "first"),
            away_team=("away_team", "first"),
            kickoff_at=("kickoff_parsed", "first"),
            home_handicap_median=("home_handicap_numeric", "median"),
            home_price_probability_median=("home_price_probability", "median"),
            bookmaker_count=("bookmaker_id", "nunique"),
        )
        .reset_index()
        .sort_values(["match_id", "captured_at", "snapshot_id"], kind="mergesort")
    )

    rows: list[dict[str, Any]] = []
    for match_id, group in snapshots.groupby("match_id", sort=False):
        ordered = group.sort_values(["captured_at", "snapshot_id"], kind="mergesort")
        opening = ordered.iloc[0]
        latest = ordered.iloc[-1]
        hours = max(
            0.0,
            float((latest["captured_at"] - opening["captured_at"]).total_seconds() / 3600.0),
        )
        # Asian handicap convention: a more negative home line means stronger
        # home support, e.g. -0.75 -> -1.00 yields +0.25 strength.
        line_strength = float(opening["home_handicap_median"] - latest["home_handicap_median"])
        price_delta = float(
            latest["home_price_probability_median"] - opening["home_price_probability_median"]
        )
        rows.append(
            {
                "match_id": match_id,
                "source_fixture_id": latest["source_fixture_id"],
                "competition_id": latest["competition_id"],
                "home_team": latest["home_team"],
                "away_team": latest["away_team"],
                "kickoff_at": pd.Timestamp(latest["kickoff_at"]).isoformat(),
                "snapshot_count": int(len(ordered)),
                "bookmaker_count": int(ordered["bookmaker_count"].max()),
                "opening_captured_at": pd.Timestamp(opening["captured_at"]).isoformat(),
                "latest_captured_at": pd.Timestamp(latest["captured_at"]).isoformat(),
                "movement_hours": round(hours, 6),
                "opening_home_handicap_median": float(opening["home_handicap_median"]),
                "latest_home_handicap_median": float(latest["home_handicap_median"]),
                "home_line_strength_delta": round(line_strength, 6),
                "opening_home_price_probability_median": float(opening["home_price_probability_median"]),
                "latest_home_price_probability_median": float(latest["home_price_probability_median"]),
                "home_price_probability_delta": round(price_delta, 6),
                "line_strength_per_hour": round(line_strength / hours, 6) if hours > 0 else 0.0,
                "favorite_hot_without_line_support": bool(
                    price_delta >= 0.03 and line_strength < 0.125
                ),
                "line_upgrade_without_price_support": bool(
                    line_strength >= 0.25 and price_delta <= 0.0
                ),
                "line_downgrade": bool(line_strength <= -0.25),
                "safe_for_shadow_features": bool(len(ordered) >= 2 and hours > 0),
            }
        )
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
