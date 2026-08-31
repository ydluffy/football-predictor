from __future__ import annotations

import numpy as np
import pandas as pd


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").astype(float)


def _extract_open_last(df: pd.DataFrame, base: str) -> tuple[pd.Series, pd.Series]:
    open_col = f"{base}_open"
    last_col = f"{base}_last"
    close_col = f"{base}_close"
    if open_col in df.columns and last_col in df.columns:
        return _num(df, open_col), _num(df, last_col)
    if open_col in df.columns and close_col in df.columns:
        return _num(df, open_col), _num(df, close_col)
    if base in df.columns and last_col in df.columns:
        return _num(df, base), _num(df, last_col)
    if base in df.columns and close_col in df.columns:
        return _num(df, base), _num(df, close_col)

    t_cols = [c for c in df.columns if c.startswith(f"{base}_t")]
    if t_cols:
        def _t_idx(name: str) -> int:
            suf = name.split("_t", 1)[-1]
            try:
                return int(suf)
            except ValueError:
                return 10**9

        ordered = [c for c in sorted(t_cols, key=_t_idx) if _t_idx(c) != 10**9]
        if ordered:
            return _num(df, ordered[0]), _num(df, ordered[-1])

    base_col = base
    if base_col in df.columns:
        s = _num(df, base_col)
        return s, s
    return pd.Series(np.nan, index=df.index, dtype=float), pd.Series(np.nan, index=df.index, dtype=float)


def _norm_implied_from_odds(odds_home: pd.Series, odds_draw: pd.Series, odds_away: pd.Series) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    eps = 1e-12
    oh = odds_home.to_numpy(dtype=float, copy=False)
    od = odds_draw.to_numpy(dtype=float, copy=False)
    oa = odds_away.to_numpy(dtype=float, copy=False)
    valid = np.isfinite(oh) & np.isfinite(od) & np.isfinite(oa) & (oh > 0.0) & (od > 0.0) & (oa > 0.0)

    nh = np.zeros_like(oh, dtype=float)
    nd = np.zeros_like(oh, dtype=float)
    na = np.zeros_like(oh, dtype=float)
    if valid.any():
        imp_h = 1.0 / np.clip(oh[valid], eps, None)
        imp_d = 1.0 / np.clip(od[valid], eps, None)
        imp_a = 1.0 / np.clip(oa[valid], eps, None)
        s = np.clip(imp_h + imp_d + imp_a, eps, None)
        nh[valid] = imp_h / s
        nd[valid] = imp_d / s
        na[valid] = imp_a / s
    return nh, nd, na, valid


def build_kelly_proxy_features(df: pd.DataFrame) -> pd.DataFrame:
    idx = df.index

    h_o, h_l = _extract_open_last(df, "odds_home")
    d_o, d_l = _extract_open_last(df, "odds_draw")
    a_o, a_l = _extract_open_last(df, "odds_away")

    n_h_o, n_d_o, n_a_o, valid_open = _norm_implied_from_odds(h_o, d_o, a_o)
    n_h_l, n_d_l, n_a_l, valid_last = _norm_implied_from_odds(h_l, d_l, a_l)
    valid = valid_open & valid_last

    proxy_h = pd.Series(n_h_l, index=idx, dtype=float)
    proxy_d = pd.Series(n_d_l, index=idx, dtype=float)
    proxy_a = pd.Series(n_a_l, index=idx, dtype=float)

    delta_h = pd.Series(n_h_l - n_h_o, index=idx, dtype=float)
    delta_d = pd.Series(n_d_l - n_d_o, index=idx, dtype=float)
    delta_a = pd.Series(n_a_l - n_a_o, index=idx, dtype=float)

    dir_h = pd.Series(np.sign(delta_h.to_numpy(dtype=float, copy=False)), index=idx, dtype=float).astype(int)
    dir_d = pd.Series(np.sign(delta_d.to_numpy(dtype=float, copy=False)), index=idx, dtype=float).astype(int)
    dir_a = pd.Series(np.sign(delta_a.to_numpy(dtype=float, copy=False)), index=idx, dtype=float).astype(int)

    proxy_stack = np.stack([proxy_h.to_numpy(), proxy_d.to_numpy(), proxy_a.to_numpy()], axis=1)
    delta_stack = np.stack([delta_h.to_numpy(), delta_d.to_numpy(), delta_a.to_numpy()], axis=1)
    spread = pd.Series(proxy_stack.max(axis=1) - proxy_stack.min(axis=1), index=idx, dtype=float)
    max_shift = pd.Series(np.abs(delta_stack).max(axis=1), index=idx, dtype=float)

    out = pd.DataFrame(
        {
            "kelly_proxy_home": proxy_h.where(valid, 0.0),
            "kelly_proxy_draw": proxy_d.where(valid, 0.0),
            "kelly_proxy_away": proxy_a.where(valid, 0.0),
            "delta_kelly_proxy_home": delta_h.where(valid, 0.0),
            "delta_kelly_proxy_draw": delta_d.where(valid, 0.0),
            "delta_kelly_proxy_away": delta_a.where(valid, 0.0),
            "kelly_direction_home": dir_h.where(valid, 0),
            "kelly_direction_draw": dir_d.where(valid, 0),
            "kelly_direction_away": dir_a.where(valid, 0),
            "kelly_proxy_spread": spread.where(valid, 0.0),
            "kelly_proxy_max_shift": max_shift.where(valid, 0.0),
        },
        index=idx,
    )

    out = out.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return out
