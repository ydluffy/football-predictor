from __future__ import annotations

import pandas as pd


_ACTUAL_RESULT_MAP = {
    "HOME": "home",
    "H": "home",
    "1": "home",
    "DRAW": "draw",
    "D": "draw",
    "X": "draw",
    "AWAY": "away",
    "A": "away",
    "2": "away",
}


def parse_match_dates(series: pd.Series) -> pd.Series:
    raw = series.astype("string").str.strip()
    parsed = pd.to_datetime(raw, format="%Y-%m-%d", errors="coerce")

    remaining = parsed.isna() & raw.notna()
    if remaining.any():
        parsed.loc[remaining] = pd.to_datetime(
            raw.loc[remaining],
            format="%d/%m/%Y",
            errors="coerce",
        )

    remaining = parsed.isna() & raw.notna()
    if remaining.any():
        parsed.loc[remaining] = pd.to_datetime(
            raw.loc[remaining],
            format="%d/%m/%y",
            errors="coerce",
        )

    remaining = parsed.isna() & raw.notna()
    if remaining.any():
        parsed.loc[remaining] = pd.to_datetime(
            raw.loc[remaining],
            errors="coerce",
            dayfirst=True,
        )
    return parsed


def standardize_dataset_values(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    if "date" in out.columns:
        dt = parse_match_dates(out["date"])
        out["date"] = dt.dt.date.astype("string")

    if "injury_flag" in out.columns:
        s = pd.to_numeric(out["injury_flag"], errors="coerce")
        out["injury_flag"] = s.where(s.isin([0, 1]), pd.NA).astype("Int64")

    if "actual_result" in out.columns:
        s = out["actual_result"].astype(str).str.strip().str.upper()
        out["actual_result"] = s.map(_ACTUAL_RESULT_MAP).astype("string")

    for c in (
        "odds_home",
        "odds_draw",
        "odds_away",
        "odds_home_open",
        "odds_draw_open",
        "odds_away_open",
        "odds_home_last",
        "odds_draw_last",
        "odds_away_last",
        "xg_home",
        "xg_away",
        "line_move",
        "home_goals",
        "away_goals",
        "home_shots",
        "away_shots",
        "home_shots_on_target",
        "away_shots_on_target",
        "home_corners",
        "away_corners",
        "home_yellow_cards",
        "away_yellow_cards",
        "home_red_cards",
        "away_red_cards",
    ):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").astype(float)

    return out
