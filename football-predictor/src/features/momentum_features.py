from __future__ import annotations

import numpy as np
import pandas as pd


def exp_decay_mean(values: list[float], decay: float = 0.85) -> float:
    d = float(decay)
    if d <= 0.0 or d >= 1.0:
        raise ValueError("decay 必须在 (0,1) 区间内")
    if not values:
        return 0.0

    weights = []
    cleaned = []
    for i, v in enumerate(values):
        if v is None:
            continue
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(x):
            continue
        w = d ** float(i)
        weights.append(w)
        cleaned.append(x)

    if not cleaned:
        return 0.0
    w_sum = float(sum(weights))
    if w_sum == 0.0:
        return 0.0
    return float(sum(w * x for w, x in zip(weights, cleaned)) / w_sum)


def _get_hist(df: pd.DataFrame, prefix: str, k: int = 3) -> list[pd.Series]:
    out = []
    for i in range(1, k + 1):
        col = f"{prefix}{i}"
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce").astype(float)
        else:
            s = pd.Series(np.nan, index=df.index, dtype=float)
        out.append(s)
    return out


def build_momentum_features(df: pd.DataFrame, decay: float = 0.85) -> pd.DataFrame:
    home_xg = _get_hist(df, "home_xg_last_", 3)
    away_xg = _get_hist(df, "away_xg_last_", 3)
    home_xga = _get_hist(df, "home_xga_last_", 3)
    away_xga = _get_hist(df, "away_xga_last_", 3)

    def _rowwise(series_list: list[pd.Series]) -> pd.Series:
        arr = np.stack([s.to_numpy(dtype=float, copy=False) for s in series_list], axis=1)
        out = np.zeros(arr.shape[0], dtype=float)
        for r in range(arr.shape[0]):
            vals = [arr[r, 0], arr[r, 1], arr[r, 2]]
            out[r] = exp_decay_mean(vals, decay=float(decay))
        return pd.Series(out, index=df.index, dtype=float)

    home_attack = _rowwise(home_xg)
    away_attack = _rowwise(away_xg)
    home_def = _rowwise(home_xga)
    away_def = _rowwise(away_xga)

    out = pd.DataFrame(
        {
            "home_attack_momentum": home_attack,
            "away_attack_momentum": away_attack,
            "home_defense_momentum": home_def,
            "away_defense_momentum": away_def,
            "attack_momentum_diff": home_attack - away_attack,
            "defense_momentum_diff": home_def - away_def,
        },
        index=df.index,
    )
    out = out.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return out
