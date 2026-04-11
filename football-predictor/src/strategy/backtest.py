from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from strategy.staking import kelly_fractional, kelly_full, stake_amount
from strategy.value import edge, expected_value, implied_prob_from_odds


@dataclass(frozen=True)
class BacktestConfig:
    ev_threshold: float = 0.02
    edge_threshold: float = 0.01
    prob_threshold: float = 0.15
    kelly_fraction: float = 0.25
    max_stake_fraction: float = 0.03
    initial_bankroll: float = 1000.0


def _coerce_date(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series, errors="coerce")
    return dt


def prepare_frame(*, pred_df: pd.DataFrame, matches_df: pd.DataFrame) -> pd.DataFrame:
    if pred_df.empty:
        raise ValueError("pred_df 为空")
    if matches_df.empty:
        raise ValueError("matches_df 为空")
    if "match_id" not in pred_df.columns:
        raise ValueError("pred_df 缺少 match_id")
    if "match_id" not in matches_df.columns:
        raise ValueError("matches_df 缺少 match_id")

    m = matches_df.copy()
    m["match_id"] = m["match_id"].astype(str)
    keep = ["match_id", "date", "league", "odds_home", "odds_draw", "odds_away", "actual_result"]
    missing = [c for c in keep if c not in m.columns]
    if missing:
        raise ValueError(f"matches_df 缺少字段: {missing}")
    m2 = m[keep].copy()
    m2 = m2.rename(columns={"actual_result": "actual"})

    p = pred_df.copy()
    p["match_id"] = p["match_id"].astype(str)
    required_pred = ["p_home", "p_draw", "p_away"]
    miss_pred = [c for c in required_pred if c not in p.columns]
    if miss_pred:
        raise ValueError(f"pred_df 缺少字段: {miss_pred}")

    df = p.merge(m2, how="left", on="match_id", suffixes=("", "_m"))
    if df["odds_home"].isna().all() and df["odds_draw"].isna().all() and df["odds_away"].isna().all():
        raise ValueError("merge 失败：无法从 matches_df 补齐 odds_*")

    if "date" in df.columns:
        df["date"] = _coerce_date(df["date"])
    else:
        raise ValueError("merge 失败：缺少 date")

    if df["date"].isna().any():
        df = df.loc[df["date"].notna(), :].copy()
    if df.empty:
        raise ValueError("date 无法解析导致无可用样本")

    return df


def _side_table(df: pd.DataFrame, *, kelly_fraction: float) -> pd.DataFrame:
    sides = [
        ("H", "p_home", "odds_home"),
        ("D", "p_draw", "odds_draw"),
        ("A", "p_away", "odds_away"),
    ]
    rows = []
    for side, p_col, o_col in sides:
        tmp = df[["match_id", "date", "league", "actual", p_col, o_col]].copy()
        tmp = tmp.rename(columns={p_col: "model_prob", o_col: "odds"})
        tmp["side"] = side
        tmp["implied_prob"] = implied_prob_from_odds(tmp["odds"])
        tmp["edge"] = edge(tmp["model_prob"], tmp["implied_prob"])
        tmp["ev"] = expected_value(tmp["model_prob"], tmp["odds"])
        tmp["kelly_full"] = kelly_full(tmp["model_prob"], tmp["odds"])
        tmp["kelly_frac"] = kelly_fractional(tmp["kelly_full"], fraction=float(kelly_fraction))
        rows.append(tmp)
    out = pd.concat(rows, ignore_index=True)
    return out


def select_bets(df: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    tbl = _side_table(df, kelly_fraction=cfg.kelly_fraction)
    tbl = tbl.replace([np.inf, -np.inf], np.nan)
    tbl = tbl.loc[tbl["odds"].notna() & (tbl["odds"] > 1.0), :].copy()

    mask = (
        (tbl["ev"] > float(cfg.ev_threshold))
        & (tbl["edge"] > float(cfg.edge_threshold))
        & (tbl["model_prob"] > float(cfg.prob_threshold))
    )
    cand = tbl.loc[mask, :].copy()
    if cand.empty:
        return cand

    cand = cand.sort_values(["match_id", "ev"], ascending=[True, False], kind="mergesort")
    best = cand.groupby("match_id", as_index=False).head(1).reset_index(drop=True)
    return best


def run_backtest(*, pred_df: pd.DataFrame, matches_df: pd.DataFrame, cfg: BacktestConfig) -> dict[str, Any]:
    df = prepare_frame(pred_df=pred_df, matches_df=matches_df)
    df = df.sort_values(["date", "match_id"], kind="mergesort").reset_index(drop=True)

    chosen = select_bets(df, cfg)
    chosen = chosen.set_index("match_id") if not chosen.empty else chosen

    bankroll = float(cfg.initial_bankroll)
    peak = float(cfg.initial_bankroll)
    bets_rows: list[dict[str, object]] = []
    curve_rows: list[dict[str, object]] = []

    for i, r in df.iterrows():
        mid = str(r["match_id"])
        dt = r["date"]
        league = r.get("league")
        bankroll_before = bankroll
        pnl = 0.0
        placed = False

        if not chosen.empty and mid in chosen.index:
            pick = chosen.loc[mid]
            if isinstance(pick, pd.DataFrame):
                pick = pick.iloc[0]
            side = str(pick["side"])
            model_prob = float(pick["model_prob"])
            odds = float(pick["odds"])
            implied_prob = float(pick["implied_prob"])
            edge_v = float(pick["edge"])
            ev_v = float(pick["ev"])
            k_full = float(pick["kelly_full"]) if pd.notna(pick["kelly_full"]) else 0.0
            k_frac = float(pick["kelly_frac"]) if pd.notna(pick["kelly_frac"]) else 0.0
            stake = stake_amount(bankroll=bankroll, kelly_frac=k_frac, max_fraction=cfg.max_stake_fraction)
            if stake > 0.0:
                placed = True
                actual = str(r.get("actual") or "").upper()
                actual_win = bool(actual == side)
                if actual_win:
                    pnl = stake * (odds - 1.0)
                else:
                    pnl = -stake
                bankroll = bankroll + pnl
                bets_rows.append(
                    {
                        "match_id": mid,
                        "date": str(dt.date()) if hasattr(dt, "date") else str(dt),
                        "league": str(league) if league is not None else None,
                        "side": side,
                        "model_prob": model_prob,
                        "odds": odds,
                        "implied_prob": implied_prob,
                        "edge": edge_v,
                        "ev": ev_v,
                        "kelly_full": k_full,
                        "kelly_frac": k_frac,
                        "stake": float(stake),
                        "actual_win": bool(actual_win),
                        "pnl": float(pnl),
                        "bankroll_before": float(bankroll_before),
                        "bankroll_after": float(bankroll),
                    }
                )

        if bankroll > peak:
            peak = bankroll
        drawdown = (peak - bankroll) / peak if peak > 0 else 0.0
        curve_rows.append(
            {
                "step": int(i + 1),
                "date": str(dt.date()) if hasattr(dt, "date") else str(dt),
                "bankroll": float(bankroll),
                "drawdown": float(drawdown),
                "placed_bet": bool(placed),
            }
        )

    bets_df = pd.DataFrame(bets_rows)
    curve_df = pd.DataFrame(curve_rows)

    total_staked = float(bets_df["stake"].sum()) if not bets_df.empty else 0.0
    profit = float(bankroll - float(cfg.initial_bankroll))
    roi = float(profit / total_staked) if total_staked > 0 else 0.0
    hit_rate = float(bets_df["actual_win"].mean()) if not bets_df.empty else 0.0
    max_drawdown = float(curve_df["drawdown"].max()) if not curve_df.empty else 0.0

    by_league = pd.DataFrame(columns=["league", "n_bets", "profit", "roi", "hit_rate"])
    if not bets_df.empty and "league" in bets_df.columns:
        g = bets_df.groupby("league", dropna=False)
        rows = []
        for lg, grp in g:
            st = float(grp["stake"].sum())
            pf = float(grp["pnl"].sum())
            rows.append(
                {
                    "league": str(lg) if lg is not None else None,
                    "n_bets": int(len(grp)),
                    "profit": pf,
                    "roi": float(pf / st) if st > 0 else 0.0,
                    "hit_rate": float(grp["actual_win"].mean()) if len(grp) else 0.0,
                }
            )
        by_league = pd.DataFrame(rows).sort_values(["n_bets", "league"], ascending=[False, True], kind="mergesort").reset_index(drop=True)

    summary = {
        "n_bets": int(len(bets_df)),
        "profit": float(profit),
        "roi": float(roi),
        "hit_rate": float(hit_rate),
        "max_drawdown": float(max_drawdown),
        "final_bankroll": float(bankroll),
    }

    return {"bets": bets_df, "equity_curve": curve_df.drop(columns=["placed_bet"], errors="ignore"), "by_league": by_league, "summary": summary}
