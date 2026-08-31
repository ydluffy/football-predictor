from __future__ import annotations

import numpy as np
import pandas as pd


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").astype(float)


def _delta_open_last(df: pd.DataFrame, base: str) -> pd.Series:
    o = _num(df, f"{base}_open")
    if o.isna().all():
        o = _num(df, base)
    l = _num(df, f"{base}_last")
    valid = o.notna() & l.notna()
    return (l - o).where(valid, 0.0)


def _pct_open_last(df: pd.DataFrame, base: str, delta: pd.Series) -> pd.Series:
    o = _num(df, f"{base}_open")
    if o.isna().all():
        o = _num(df, base)
    valid = o.notna() & (o != 0.0)
    return (delta / o.where(valid, np.nan)).where(valid, 0.0)


def _drop_flag(delta: pd.Series, *, valid: pd.Series) -> pd.Series:
    return (delta < 0.0).where(valid, False).astype(int)


def _recent_move(df: pd.DataFrame, base: str) -> pd.Series:
    t1 = _num(df, f"{base}_t1")
    t2 = _num(df, f"{base}_t2")
    valid = t1.notna() & t2.notna()
    return (t2 - t1).where(valid, 0.0)


def build_odds_sequence_features(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)

    bases = {
        "home": "odds_home",
        "draw": "odds_draw",
        "away": "odds_away",
    }

    deltas: dict[str, pd.Series] = {}
    valids: dict[str, pd.Series] = {}
    for key, base in bases.items():
        o = _num(df, f"{base}_open")
        if o.isna().all():
            o = _num(df, base)
        l = _num(df, f"{base}_last")
        valid = o.notna() & l.notna()
        valids[key] = valid

        d = (l - o).where(valid, 0.0)
        deltas[key] = d
        out[f"delta_{key}_open_last"] = d
        out[f"pct_{key}_open_last"] = _pct_open_last(df, base, d)
        out[f"{key}_odds_drop_flag"] = _drop_flag(d, valid=valid)

    abs_d = pd.concat([deltas["home"].abs(), deltas["draw"].abs(), deltas["away"].abs()], axis=1)
    out["odds_move_abs_sum"] = abs_d.sum(axis=1).astype(float)
    out["odds_move_max_abs"] = abs_d.max(axis=1).astype(float)

    out["recent_home_move"] = _recent_move(df, "odds_home")
    out["recent_draw_move"] = _recent_move(df, "odds_draw")
    out["recent_away_move"] = _recent_move(df, "odds_away")

    out = out.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return out
