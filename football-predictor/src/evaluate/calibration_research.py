from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd

from data.competition_registry import CompetitionRegistry, load_competition_registry
from evaluate.bootstrap import paired_bootstrap_logloss_difference
from evaluate.metrics import compute_metrics, expected_calibration_error
from features.basic_features import build_basic_features
from models.calibration import fit_calibrator, predict_calibrated_proba
from models.model_factory import predict_model_proba, train_model


PROBA_COLUMNS = ["p_home", "p_draw", "p_away"]


def run_calibration_research(
    matches: pd.DataFrame,
    *,
    competition_labels: Iterable[str],
    competition_col: str = "league",
    feature_version: str = "v1",
    model_type: str = "logit",
    calibration_method: str = "sigmoid",
    min_train_seasons: int = 2,
    n_bootstrap: int = 5000,
    random_state: int = 42,
    n_bins: int = 10,
    registry: CompetitionRegistry | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    if model_type != "logit":
        raise ValueError("calibration research currently supports logit only")
    required = {competition_col, "season", "date", "match_id"}
    missing = required - set(matches.columns)
    if missing:
        raise ValueError(f"missing calibration research columns: {sorted(missing)}")

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
                {
                    "source_label": label,
                    "rows": int(len(data)),
                    "season_count": len(seasons),
                    "reason": "insufficient_seasons",
                }
            )
            continue

        X_all, y_all, _ = build_basic_features(data, feature_version=feature_version)
        oos_truth: list[str] = []
        oos_raw: list[np.ndarray] = []
        oos_calibrated: list[np.ndarray] = []
        oos_market: list[np.ndarray] = []
        competition_fold_rows: list[dict[str, Any]] = []

        for holdout_index in range(int(min_train_seasons), len(seasons)):
            holdout = seasons[holdout_index]
            train_seasons = seasons[:holdout_index]
            train_mask = data["season"].astype(str).isin(train_seasons)
            test_mask = data["season"].astype(str).eq(holdout)
            if not train_mask.any() or not test_mask.any():
                continue

            model = train_model(model_type, X_all.loc[train_mask], y_all.loc[train_mask])
            raw = predict_model_proba(model_type, model, X_all.loc[test_mask])
            estimator = model.sklearn_estimator
            calibrator = fit_calibrator(
                estimator,
                X_all.loc[train_mask],
                y_all.loc[train_mask],
                method=calibration_method,
                cv=3,
            )
            calibrated = predict_calibrated_proba(calibrator, X_all.loc[test_mask])
            market = X_all.loc[test_mask, ["norm_home", "norm_draw", "norm_away"]].copy()
            market.columns = PROBA_COLUMNS
            truth = y_all.loc[test_mask]

            raw_metrics = compute_metrics(truth, raw)
            calibrated_metrics = compute_metrics(truth, calibrated)
            market_metrics = compute_metrics(truth, market)
            row = {
                "competition_id": str(registry.annotate(label)["competition_id"]),
                "source_label": label,
                "holdout_season": holdout,
                "train_seasons": ",".join(train_seasons),
                "train_size": int(train_mask.sum()),
                "test_size": int(test_mask.sum()),
                "raw_logloss": float(raw_metrics["logloss"]),
                "calibrated_logloss": float(calibrated_metrics["logloss"]),
                "market_logloss": float(market_metrics["logloss"]),
                "raw_logloss_vs_market": float(raw_metrics["logloss"] - market_metrics["logloss"]),
                "calibrated_logloss_vs_market": float(
                    calibrated_metrics["logloss"] - market_metrics["logloss"]
                ),
                "raw_brier": float(raw_metrics["brier"]),
                "calibrated_brier": float(calibrated_metrics["brier"]),
                "market_brier": float(market_metrics["brier"]),
                "raw_ece": expected_calibration_error(truth, raw, n_bins=n_bins),
                "calibrated_ece": expected_calibration_error(truth, calibrated, n_bins=n_bins),
                "market_ece": expected_calibration_error(truth, market, n_bins=n_bins),
            }
            competition_fold_rows.append(row)
            fold_rows.append(row)
            oos_truth.extend(truth.astype(str).tolist())
            oos_raw.append(raw.to_numpy(dtype=float))
            oos_calibrated.append(calibrated.to_numpy(dtype=float))
            oos_market.append(market.to_numpy(dtype=float))

        if not competition_fold_rows:
            skipped.append({"source_label": label, "rows": int(len(data)), "reason": "no_holdouts"})
            continue

        raw_bootstrap = paired_bootstrap_logloss_difference(
            oos_truth,
            np.vstack(oos_raw),
            np.vstack(oos_market),
            n_bootstrap=n_bootstrap,
            random_state=random_state,
        )
        calibrated_bootstrap = paired_bootstrap_logloss_difference(
            oos_truth,
            np.vstack(oos_calibrated),
            np.vstack(oos_market),
            n_bootstrap=n_bootstrap,
            random_state=random_state + 1,
        )
        folds = pd.DataFrame(competition_fold_rows)
        holdouts_better = int((folds["calibrated_logloss_vs_market"] < 0.0).sum())
        mean_calibrated_ece = float(folds["calibrated_ece"].mean())
        mean_market_ece = float(folds["market_ece"].mean())
        ece_std = float(folds["calibrated_ece"].std(ddof=0))
        gates = {
            "bootstrap_ci_below_zero": bool(calibrated_bootstrap["ci95_high"] < 0.0),
            "bootstrap_probability_at_least_95pct": bool(
                calibrated_bootstrap["probability_model_better"] >= 0.95
            ),
            "mean_ece_not_worse_than_market": bool(mean_calibrated_ece <= mean_market_ece),
            "ece_std_at_most_0_02": bool(ece_std <= 0.02),
            "at_least_two_holdouts_better": bool(holdouts_better >= 2),
        }
        shadow_eligible = bool(all(gates.values()))
        summaries.append(
            {
                "competition_id": str(registry.annotate(label)["competition_id"]),
                "source_label": label,
                "holdouts": int(len(folds)),
                "test_matches": int(folds["test_size"].sum()),
                "raw_bootstrap": raw_bootstrap,
                "calibrated_bootstrap": calibrated_bootstrap,
                "mean_raw_ece": float(folds["raw_ece"].mean()),
                "mean_calibrated_ece": mean_calibrated_ece,
                "mean_market_ece": mean_market_ece,
                "calibrated_ece_std": ece_std,
                "holdouts_calibrated_better_than_market": holdouts_better,
                "gates": gates,
                "shadow_eligible": shadow_eligible,
                "decision": "shadow_eligible" if shadow_eligible else "research_rejected",
            }
        )

    return pd.DataFrame(fold_rows), summaries, skipped
