from __future__ import annotations

import pandas as pd

from evaluate.metrics import compute_metrics
from features.basic_features import build_basic_features
from models.model_factory import predict_model_proba, train_model


def run_season_holdout(
    df: pd.DataFrame,
    *,
    feature_version: str = "v1",
    model_type: str = "logit",
    min_train_seasons: int = 2,
) -> pd.DataFrame:
    if "season" not in df.columns:
        raise ValueError("缺少 season 字段")

    data = df.sort_values(["date", "match_id"], kind="mergesort").reset_index(drop=True)
    seasons = sorted(data["season"].dropna().astype(str).unique())
    if len(seasons) <= min_train_seasons:
        raise ValueError("赛季数量不足，无法进行赛季留出评估")

    X_all, y_all, _ = build_basic_features(data, feature_version=feature_version)
    rows: list[dict[str, object]] = []
    for holdout_index in range(min_train_seasons, len(seasons)):
        holdout = seasons[holdout_index]
        train_seasons = seasons[:holdout_index]
        train_mask = data["season"].astype(str).isin(train_seasons)
        test_mask = data["season"].astype(str).eq(holdout)
        if not train_mask.any() or not test_mask.any():
            continue

        model = train_model(model_type, X_all.loc[train_mask], y_all.loc[train_mask])
        proba = predict_model_proba(model_type, model, X_all.loc[test_mask])
        metrics = compute_metrics(y_all.loc[test_mask], proba)

        market = X_all.loc[test_mask, ["norm_home", "norm_draw", "norm_away"]].copy()
        market.columns = ["p_home", "p_draw", "p_away"]
        market_metrics = compute_metrics(y_all.loc[test_mask], market)
        rows.append(
            {
                "holdout_season": holdout,
                "train_seasons": ",".join(train_seasons),
                "train_size": int(train_mask.sum()),
                "test_size": int(test_mask.sum()),
                "model_type": model_type,
                "feature_version": feature_version,
                "brier": float(metrics["brier"]),
                "logloss": float(metrics["logloss"]),
                "market_brier": float(market_metrics["brier"]),
                "market_logloss": float(market_metrics["logloss"]),
                "brier_vs_market": float(metrics["brier"] - market_metrics["brier"]),
                "logloss_vs_market": float(metrics["logloss"] - market_metrics["logloss"]),
            }
        )
    return pd.DataFrame(rows)
