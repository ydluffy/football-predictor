from __future__ import annotations

import pandas as pd

from evaluate.metrics import compute_metrics


def summarize_cv_by_league(df_fold_predictions: pd.DataFrame) -> pd.DataFrame:
    required = {
        "fold",
        "model_type",
        "feature_version",
        "league",
        "actual",
        "p_home",
        "p_draw",
        "p_away",
    }
    missing = sorted(required - set(df_fold_predictions.columns))
    if missing:
        raise ValueError(f"缺少字段: {missing}")

    rows: list[dict[str, object]] = []
    group_cols = ["model_type", "feature_version", "fold", "league"]
    has_cal = "calibration_method" in df_fold_predictions.columns
    if has_cal:
        group_cols.insert(2, "calibration_method")

    for _, g in df_fold_predictions.groupby(group_cols, dropna=False):
        m = compute_metrics(g["actual"], g[["p_home", "p_draw", "p_away"]])
        row: dict[str, object] = {
            "model_type": str(g["model_type"].iloc[0]),
            "feature_version": str(g["feature_version"].iloc[0]),
            "fold": int(g["fold"].iloc[0]),
            "league": str(g["league"].iloc[0]),
            "n_samples": int(len(g)),
            "brier": float(m["brier"]),
            "logloss": float(m["logloss"]),
        }
        if has_cal:
            row["calibration_method"] = str(g["calibration_method"].iloc[0])
        rows.append(row)

    out = pd.DataFrame(rows)
    order = ["model_type", "feature_version"]
    if has_cal:
        order.append("calibration_method")
    order += ["fold", "league", "n_samples", "brier", "logloss"]
    out = out[order].sort_values(["model_type", "feature_version", "fold", "league"], kind="mergesort").reset_index(drop=True)
    return out

