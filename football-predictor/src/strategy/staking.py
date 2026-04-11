from __future__ import annotations

import numpy as np
import pandas as pd


def kelly_full(model_prob: pd.Series, odds: pd.Series) -> pd.Series:
    p = pd.to_numeric(model_prob, errors="coerce").astype(float)
    o = pd.to_numeric(odds, errors="coerce").astype(float)
    denom = (o - 1.0).replace(0.0, np.nan)
    out = (p * o - 1.0) / denom
    out = out.where(np.isfinite(out), np.nan).clip(lower=0.0)
    return out


def kelly_fractional(kelly: pd.Series, fraction: float = 0.25) -> pd.Series:
    k = pd.to_numeric(kelly, errors="coerce").astype(float)
    f = float(fraction)
    out = (k * f).where(np.isfinite(k), np.nan).clip(lower=0.0)
    return out


def stake_amount(*, bankroll: float, kelly_frac: float, max_fraction: float = 0.03) -> float:
    b = float(bankroll)
    frac = float(kelly_frac)
    cap = float(max_fraction)
    if not np.isfinite(b) or b <= 0.0:
        return 0.0
    if not np.isfinite(frac) or frac <= 0.0:
        return 0.0
    if not np.isfinite(cap) or cap <= 0.0:
        return 0.0
    return b * min(frac, cap)

