from __future__ import annotations

import numpy as np
import pandas as pd


def _safe_implied_prob(odds: pd.Series) -> pd.Series:
    eps = 1e-9
    return 1.0 / (odds.clip(lower=eps))


def build_baseline_features(df: pd.DataFrame) -> pd.DataFrame:
    required = {
        "odds_home",
        "odds_draw",
        "odds_away",
        "xg_home",
        "xg_away",
        "injury_flag",
        "line_move",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"missing feature inputs: {missing}")

    p_home = _safe_implied_prob(df["odds_home"])
    p_draw = _safe_implied_prob(df["odds_draw"])
    p_away = _safe_implied_prob(df["odds_away"])
    book_sum = (p_home + p_draw + p_away).replace(0.0, np.nan)

    feat = pd.DataFrame(index=df.index)
    feat["odds_p_home"] = (p_home / book_sum).fillna(0.0)
    feat["odds_p_draw"] = (p_draw / book_sum).fillna(0.0)
    feat["odds_p_away"] = (p_away / book_sum).fillna(0.0)
    feat["odds_overround"] = (book_sum - 1.0).fillna(0.0)
    feat["xg_diff"] = (df["xg_home"] - df["xg_away"]).astype(float)
    feat["xg_sum"] = (df["xg_home"] + df["xg_away"]).astype(float)
    feat["injury_flag"] = df["injury_flag"].astype(int)
    feat["line_move"] = df["line_move"].astype(float)
    return feat


def extract_labels(df: pd.DataFrame) -> pd.Series:
    if "actual_result" not in df.columns:
        raise ValueError("missing actual_result")
    y = df["actual_result"].astype(str).str.upper()
    valid = {"H", "D", "A"}
    bad = sorted(set(y) - valid)
    if bad:
        raise ValueError(f"invalid actual_result values: {bad}")
    return y
