from __future__ import annotations

from pathlib import Path
from typing import Final

import pandas as pd


REQUIRED_COLUMNS: Final[list[str]] = [
    "match_id",
    "date",
    "league",
    "home_team",
    "away_team",
    "odds_home",
    "odds_draw",
    "odds_away",
    "xg_home",
    "xg_away",
    "injury_flag",
    "line_move",
    "actual_result",
]


def read_matches_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    df = df[REQUIRED_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"], errors="raise").dt.date
    for col in ["odds_home", "odds_draw", "odds_away", "xg_home", "xg_away", "line_move"]:
        df[col] = pd.to_numeric(df[col], errors="raise")
    df["injury_flag"] = pd.to_numeric(df["injury_flag"], errors="raise").astype(int)
    df["actual_result"] = df["actual_result"].astype(str).str.upper()
    valid = {"H", "D", "A"}
    bad = sorted(set(df["actual_result"]) - valid)
    if bad:
        raise ValueError(f"invalid actual_result values: {bad}")
    return df
