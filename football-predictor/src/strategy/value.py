from __future__ import annotations

import numpy as np
import pandas as pd


def implied_prob_from_odds(odds: pd.Series) -> pd.Series:
    o = pd.to_numeric(odds, errors="coerce").astype(float)
    out = 1.0 / o
    out = out.where(np.isfinite(out), np.nan)
    return out


def edge(model_prob: pd.Series, implied_prob: pd.Series) -> pd.Series:
    p = pd.to_numeric(model_prob, errors="coerce").astype(float)
    q = pd.to_numeric(implied_prob, errors="coerce").astype(float)
    out = p - q
    out = out.where(np.isfinite(out), np.nan)
    return out


def expected_value(model_prob: pd.Series, odds: pd.Series) -> pd.Series:
    p = pd.to_numeric(model_prob, errors="coerce").astype(float)
    o = pd.to_numeric(odds, errors="coerce").astype(float)
    out = p * o - 1.0
    out = out.where(np.isfinite(out), np.nan)
    return out

