from __future__ import annotations

import pandas as pd

from evaluate.metrics import compute_metrics


def evaluate_by_league(df_results: pd.DataFrame, league_col: str = "league") -> pd.DataFrame:
    required = {league_col, "actual", "p_home", "p_draw", "p_away"}
    missing = sorted(required - set(df_results.columns))
    if missing:
        raise ValueError(f"缺少必需字段: {missing}")

    if df_results.empty:
        raise ValueError("空数据：df_results 无任何记录")

    rows = []
    for league, g in df_results.groupby(league_col, dropna=False):
        m = compute_metrics(g["actual"], g[["p_home", "p_draw", "p_away"]])
        rows.append(
            {
                "league": str(league),
                "n_samples": int(len(g)),
                "brier": float(m["brier"]),
                "logloss": float(m["logloss"]),
            }
        )
    return pd.DataFrame(rows).sort_values(["n_samples", "league"], ascending=[False, True]).reset_index(drop=True)
