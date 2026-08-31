from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd

from data.competition_registry import CompetitionRegistry, load_competition_registry
from evaluate.bootstrap import paired_bootstrap_logloss_difference
from evaluate.metrics import compute_metrics, expected_calibration_error
from features.basic_features import build_basic_features
from models.market_residual import MarketResidualModel, PROBA_COLUMNS, select_context_features


def _market_frame(features: pd.DataFrame) -> pd.DataFrame:
    market = features[["norm_home", "norm_draw", "norm_away"]].copy()
    market.columns = PROBA_COLUMNS
    return market


def _select_nested_parameters(
    X_context: pd.DataFrame,
    y: pd.Series,
    market: pd.DataFrame,
    seasons: pd.Series,
    train_seasons: list[str],
    *,
    alpha_grid: tuple[float, ...],
    strength_grid: tuple[float, ...],
) -> tuple[float, float, float]:
    validation_season = train_seasons[-1]
    development_seasons = train_seasons[:-1]
    development_mask = seasons.astype(str).isin(development_seasons)
    validation_mask = seasons.astype(str).eq(validation_season)
    if not development_mask.any() or not validation_mask.any():
        return float(alpha_grid[-1]), 0.0, float("nan")

    candidates: list[tuple[float, float, float]] = []
    for alpha in alpha_grid:
        model = MarketResidualModel(alpha=alpha).train(
            X_context.loc[development_mask],
            y.loc[development_mask],
            market.loc[development_mask],
        )
        for strength in strength_grid:
            predicted = model.predict_proba(
                X_context.loc[validation_mask],
                market.loc[validation_mask],
                strength=strength,
            )
            logloss = float(compute_metrics(y.loc[validation_mask], predicted)["logloss"])
            candidates.append((logloss, float(strength), float(alpha)))
    validation_logloss, strength, alpha = min(candidates, key=lambda item: (item[0], item[1], -item[2]))
    return alpha, strength, validation_logloss


def run_market_residual_research(
    matches: pd.DataFrame,
    *,
    competition_labels: Iterable[str],
    competition_col: str = "league",
    feature_version: str = "v7",
    min_train_seasons: int = 2,
    alpha_grid: tuple[float, ...] = (1.0, 10.0, 100.0),
    strength_grid: tuple[float, ...] = (0.0, 0.1, 0.25, 0.5, 1.0),
    n_bootstrap: int = 5000,
    random_state: int = 42,
    registry: CompetitionRegistry | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    required = {competition_col, "season", "date", "match_id"}
    missing = required - set(matches.columns)
    if missing:
        raise ValueError(f"missing market residual columns: {sorted(missing)}")
    if not alpha_grid or not strength_grid:
        raise ValueError("residual parameter grids must not be empty")
    if any(alpha <= 0.0 for alpha in alpha_grid):
        raise ValueError("all residual alpha values must be positive")
    if any(strength < 0.0 or strength > 1.0 for strength in strength_grid):
        raise ValueError("all residual strengths must be between 0 and 1")

    registry = registry or load_competition_registry()
    selected = {str(label).strip() for label in competition_labels if str(label).strip()}
    fold_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for label in sorted(selected):
        data = matches.loc[matches[competition_col].astype(str).eq(label)].copy()
        data = data.sort_values(["date", "match_id"], kind="mergesort").reset_index(drop=True)
        seasons = sorted(data["season"].dropna().astype(str).unique().tolist())
        if len(seasons) <= int(min_train_seasons):
            skipped.append(
                {"source_label": label, "rows": int(len(data)), "reason": "insufficient_seasons"}
            )
            continue

        features, y, _ = build_basic_features(data, feature_version=feature_version)
        X_context = select_context_features(features)
        market = _market_frame(features)
        competition_folds: list[dict[str, Any]] = []
        oos_truth: list[str] = []
        oos_residual: list[np.ndarray] = []
        oos_market: list[np.ndarray] = []

        for holdout_index in range(int(min_train_seasons), len(seasons)):
            holdout = seasons[holdout_index]
            train_seasons = seasons[:holdout_index]
            train_mask = data["season"].astype(str).isin(train_seasons)
            test_mask = data["season"].astype(str).eq(holdout)
            alpha, strength, validation_logloss = _select_nested_parameters(
                X_context,
                y,
                market,
                data["season"],
                train_seasons,
                alpha_grid=alpha_grid,
                strength_grid=strength_grid,
            )
            model = MarketResidualModel(alpha=alpha).train(
                X_context.loc[train_mask], y.loc[train_mask], market.loc[train_mask]
            )
            predicted = model.predict_proba(
                X_context.loc[test_mask], market.loc[test_mask], strength=strength
            )
            residual_metrics = compute_metrics(y.loc[test_mask], predicted)
            market_metrics = compute_metrics(y.loc[test_mask], market.loc[test_mask])
            row = {
                "competition_id": str(registry.annotate(label)["competition_id"]),
                "source_label": label,
                "holdout_season": holdout,
                "train_seasons": ",".join(train_seasons),
                "validation_season": train_seasons[-1],
                "train_size": int(train_mask.sum()),
                "test_size": int(test_mask.sum()),
                "selected_alpha": alpha,
                "selected_strength": strength,
                "validation_logloss": validation_logloss,
                "residual_logloss": float(residual_metrics["logloss"]),
                "market_logloss": float(market_metrics["logloss"]),
                "logloss_vs_market": float(residual_metrics["logloss"] - market_metrics["logloss"]),
                "residual_brier": float(residual_metrics["brier"]),
                "market_brier": float(market_metrics["brier"]),
                "residual_ece": expected_calibration_error(y.loc[test_mask], predicted),
                "market_ece": expected_calibration_error(y.loc[test_mask], market.loc[test_mask]),
            }
            fold_rows.append(row)
            competition_folds.append(row)
            oos_truth.extend(y.loc[test_mask].astype(str).tolist())
            oos_residual.append(predicted.to_numpy(dtype=float))
            oos_market.append(market.loc[test_mask].to_numpy(dtype=float))

        if not competition_folds:
            skipped.append({"source_label": label, "rows": int(len(data)), "reason": "no_holdouts"})
            continue
        bootstrap = paired_bootstrap_logloss_difference(
            oos_truth,
            np.vstack(oos_residual),
            np.vstack(oos_market),
            n_bootstrap=n_bootstrap,
            random_state=random_state,
        )
        folds = pd.DataFrame(competition_folds)
        better_holdouts = int((folds["logloss_vs_market"] < 0.0).sum())
        nonzero_strength_holdouts = int((folds["selected_strength"] > 0.0).sum())
        gates = {
            "bootstrap_ci_below_zero": bool(bootstrap["ci95_high"] < 0.0),
            "bootstrap_probability_at_least_95pct": bool(bootstrap["probability_model_better"] >= 0.95),
            "at_least_two_holdouts_better": bool(better_holdouts >= 2),
            "nonzero_strength_in_two_holdouts": bool(nonzero_strength_holdouts >= 2),
            "mean_ece_not_worse_than_market": bool(
                folds["residual_ece"].mean() <= folds["market_ece"].mean()
            ),
        }
        shadow_eligible = bool(all(gates.values()))
        summaries.append(
            {
                "competition_id": str(registry.annotate(label)["competition_id"]),
                "source_label": label,
                "holdouts": int(len(folds)),
                "test_matches": int(folds["test_size"].sum()),
                "context_feature_count": int(X_context.shape[1]),
                "context_features": list(X_context.columns),
                "bootstrap": bootstrap,
                "holdouts_better_than_market": better_holdouts,
                "nonzero_strength_holdouts": nonzero_strength_holdouts,
                "mean_residual_ece": float(folds["residual_ece"].mean()),
                "mean_market_ece": float(folds["market_ece"].mean()),
                "gates": gates,
                "shadow_eligible": shadow_eligible,
                "decision": "shadow_eligible" if shadow_eligible else "research_rejected",
            }
        )
    return pd.DataFrame(fold_rows), summaries, skipped
