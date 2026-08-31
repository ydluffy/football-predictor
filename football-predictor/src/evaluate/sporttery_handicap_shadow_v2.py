from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from evaluate.metrics import compute_metrics, expected_calibration_error
from evaluate.sporttery_handicap_model import (
    DEFAULT_HANDICAPS,
    RQSPF_CLASSES,
    _cluster_bootstrap,
    actual_rqspf_result,
    aligned_margin_probabilities,
    build_handicap_model_frame,
    empirical_line_baseline,
    make_margin_model,
    margin_to_rqspf_probabilities,
)


DEFAULT_ALPHA_GRID = (0.0, 0.10, 0.25, 0.50, 0.75)
DEFAULT_MAX_ALPHA = {-2: 0.50, -1: 0.50, 1: 0.25, 2: 0.25}


def blend_probabilities(
    baseline: np.ndarray,
    candidate: np.ndarray,
    alpha: float,
) -> np.ndarray:
    weight = float(np.clip(alpha, 0.0, 1.0))
    blended = (1.0 - weight) * np.asarray(baseline, dtype=float) + weight * np.asarray(candidate, dtype=float)
    return blended / blended.sum(axis=1, keepdims=True)


def _select_temporal_alpha(
    train: pd.DataFrame,
    *,
    handicap: int,
    alpha_grid: Sequence[float],
    max_alpha: float,
    model_c: float,
    baseline_smoothing: float,
    min_validation_improvement: float,
) -> tuple[float, dict[str, Any]]:
    seasons = sorted(train["season"].astype(str).unique().tolist())
    if len(seasons) < 2:
        return 0.0, {"reason": "insufficient_inner_seasons"}

    validation_season = seasons[-1]
    inner_train = train.loc[train["season"].astype(str).isin(seasons[:-1])].copy()
    validation = train.loc[train["season"].astype(str).eq(validation_season)].copy()
    if inner_train.empty or validation.empty or inner_train["margin_class"].nunique() < 2:
        return 0.0, {"reason": "insufficient_inner_rows"}

    model = make_margin_model(c=model_c).fit(inner_train, inner_train["margin_class"])
    candidate_margin = aligned_margin_probabilities(model, validation)
    candidate_probability = margin_to_rqspf_probabilities(candidate_margin, handicap)
    baseline_probability = empirical_line_baseline(
        inner_train,
        validation,
        handicap=handicap,
        smoothing=baseline_smoothing,
    )
    truth = validation["actual_margin"].map(lambda value: actual_rqspf_result(value, handicap))
    baseline_logloss = compute_metrics(truth, baseline_probability)["logloss"]
    trials: list[dict[str, float]] = []
    allowed = sorted({float(value) for value in alpha_grid if 0.0 <= float(value) <= float(max_alpha)} | {0.0})
    for alpha in allowed:
        probability = blend_probabilities(baseline_probability, candidate_probability, alpha)
        trials.append({"alpha": alpha, "logloss": compute_metrics(truth, probability)["logloss"]})
    best = min(trials, key=lambda row: (row["logloss"], row["alpha"]))
    improvement = float(baseline_logloss - best["logloss"])
    selected = float(best["alpha"]) if improvement >= float(min_validation_improvement) else 0.0
    return selected, {
        "reason": "selected" if selected > 0.0 else "baseline_fallback",
        "validation_season": validation_season,
        "validation_matches": int(len(validation)),
        "baseline_logloss": float(baseline_logloss),
        "best_logloss": float(best["logloss"]),
        "validation_improvement": improvement,
        "selected_alpha": selected,
        "trials": trials,
    }


def run_sporttery_handicap_shadow_v2(
    matches: pd.DataFrame,
    *,
    handicaps: Iterable[int] = DEFAULT_HANDICAPS,
    min_train_seasons: int = 2,
    model_c: float = 0.5,
    baseline_smoothing: float = 20.0,
    alpha_grid: Sequence[float] = DEFAULT_ALPHA_GRID,
    max_alpha_by_handicap: Mapping[int, float] | None = None,
    min_validation_improvement: float = 0.0005,
    n_bootstrap: int = 2000,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Evaluate a conservative, time-selected shadow blend without changing production.

    The candidate margin model is only allowed to move the empirical market-line
    baseline when it improved the immediately preceding season. Positive handicaps
    have a lower maximum weight because v1 was unstable there in the latest holdout.
    """
    frame, audit = build_handicap_model_frame(matches)
    seasons = sorted(frame["season"].astype(str).unique().tolist())
    handicap_values = tuple(int(value) for value in handicaps)
    max_alpha_map = dict(DEFAULT_MAX_ALPHA)
    if max_alpha_by_handicap:
        max_alpha_map.update({int(key): float(value) for key, value in max_alpha_by_handicap.items()})

    prediction_parts: list[pd.DataFrame] = []
    fold_rows: list[dict[str, Any]] = []
    alpha_audit: list[dict[str, Any]] = []
    for holdout_index in range(int(min_train_seasons), len(seasons)):
        holdout = seasons[holdout_index]
        train_seasons = seasons[:holdout_index]
        train = frame.loc[frame["season"].astype(str).isin(train_seasons)].copy()
        test = frame.loc[frame["season"].astype(str).eq(holdout)].copy()
        model = make_margin_model(c=model_c).fit(train, train["margin_class"])
        candidate_margin = aligned_margin_probabilities(model, test)

        for handicap in handicap_values:
            alpha, selection = _select_temporal_alpha(
                train,
                handicap=handicap,
                alpha_grid=alpha_grid,
                max_alpha=max_alpha_map.get(handicap, 0.0),
                model_c=model_c,
                baseline_smoothing=baseline_smoothing,
                min_validation_improvement=min_validation_improvement,
            )
            alpha_audit.append({"holdout_season": holdout, "sporttery_handicap": handicap, **selection})
            raw_probability = margin_to_rqspf_probabilities(candidate_margin, handicap)
            baseline_probability = empirical_line_baseline(
                train, test, handicap=handicap, smoothing=baseline_smoothing
            )
            shadow_probability = blend_probabilities(baseline_probability, raw_probability, alpha)
            truth = test["actual_margin"].map(lambda value: actual_rqspf_result(value, handicap))
            shadow_metrics = compute_metrics(truth, shadow_probability)
            baseline_metrics = compute_metrics(truth, baseline_probability)
            fold_rows.append(
                {
                    "holdout_season": holdout,
                    "train_seasons": ",".join(train_seasons),
                    "train_matches": int(len(train)),
                    "test_matches": int(len(test)),
                    "sporttery_handicap": handicap,
                    "selected_alpha": alpha,
                    "shadow_logloss": shadow_metrics["logloss"],
                    "baseline_logloss": baseline_metrics["logloss"],
                    "logloss_vs_baseline": shadow_metrics["logloss"] - baseline_metrics["logloss"],
                    "shadow_brier": shadow_metrics["brier"],
                    "baseline_brier": baseline_metrics["brier"],
                    "shadow_ece": expected_calibration_error(truth, shadow_probability),
                    "baseline_ece": expected_calibration_error(truth, baseline_probability),
                }
            )

            part = test[["match_id", "date", "season", "league", "home_team", "away_team", "actual_margin", "opening_ah_line"]].copy()
            part["sporttery_handicap"] = handicap
            part["actual_rqspf"] = truth.to_numpy()
            part["selected_alpha"] = alpha
            for index, label in enumerate(RQSPF_CLASSES):
                part[f"shadow_probability_{label.lower()}"] = shadow_probability[:, index]
                part[f"baseline_probability_{label.lower()}"] = baseline_probability[:, index]
            truth_index = truth.map({"H": 0, "D": 1, "A": 2}).to_numpy(dtype=int)
            row_index = np.arange(len(part))
            part["shadow_logloss_row"] = -np.log(np.clip(shadow_probability[row_index, truth_index], 1e-15, 1.0))
            part["baseline_logloss_row"] = -np.log(np.clip(baseline_probability[row_index, truth_index], 1e-15, 1.0))
            prediction_parts.append(part)

    predictions = pd.concat(prediction_parts, ignore_index=True) if prediction_parts else pd.DataFrame()
    folds = pd.DataFrame(fold_rows)
    if predictions.empty:
        raise ValueError("no rolling season holdout predictions were produced")
    predictions["logloss_difference"] = predictions["shadow_logloss_row"] - predictions["baseline_logloss_row"]
    match_difference = predictions.groupby("match_id")["logloss_difference"].mean()
    bootstrap = _cluster_bootstrap(match_difference, n_bootstrap=n_bootstrap, random_state=random_state)

    handicap_summaries: list[dict[str, Any]] = []
    for handicap, group in predictions.groupby("sporttery_handicap", sort=True):
        truth = group["actual_rqspf"]
        shadow_probability = group[["shadow_probability_h", "shadow_probability_d", "shadow_probability_a"]].to_numpy()
        baseline_probability = group[["baseline_probability_h", "baseline_probability_d", "baseline_probability_a"]].to_numpy()
        shadow_metrics = compute_metrics(truth, shadow_probability)
        baseline_metrics = compute_metrics(truth, baseline_probability)
        handicap_summaries.append(
            {
                "sporttery_handicap": int(handicap),
                "scenario_rows": int(len(group)),
                "shadow_logloss": shadow_metrics["logloss"],
                "baseline_logloss": baseline_metrics["logloss"],
                "logloss_vs_baseline": shadow_metrics["logloss"] - baseline_metrics["logloss"],
                "shadow_brier": shadow_metrics["brier"],
                "baseline_brier": baseline_metrics["brier"],
                "shadow_ece": expected_calibration_error(truth, shadow_probability),
                "baseline_ece": expected_calibration_error(truth, baseline_probability),
            }
        )
    summaries = pd.DataFrame(handicap_summaries)
    league_summary = predictions.groupby("league", sort=True).agg(
        scenario_rows=("match_id", "size"),
        oos_matches=("match_id", "nunique"),
        logloss_vs_baseline=("logloss_difference", "mean"),
    ).reset_index()
    recent_holdouts = seasons[-2:]
    recent_folds = folds.loc[folds["holdout_season"].isin(recent_holdouts)]
    gates = {
        "cluster_bootstrap_ci_below_zero": bool(bootstrap["ci95_high"] < 0.0),
        "cluster_bootstrap_probability_at_least_95pct": bool(bootstrap["probability_model_better"] >= 0.95),
        "last_two_holdouts_all_handicaps_not_worse": bool(
            len(recent_folds) == len(recent_holdouts) * len(handicap_values)
            and (recent_folds["logloss_vs_baseline"] <= 0.0).all()
        ),
        "all_leagues_not_worse": bool((league_summary["logloss_vs_baseline"] <= 0.0).all()),
        "mean_ece_not_worse": bool(summaries["shadow_ece"].mean() <= summaries["baseline_ece"].mean()),
        "historical_sporttery_odds_time_aligned": False,
        "independent_settled_shadow_plans_at_least_300": False,
    }
    statistical_gates = [key for key in gates if key not in {"historical_sporttery_odds_time_aligned", "independent_settled_shadow_plans_at_least_300"}]
    statistical_gate_passed = bool(all(gates[key] for key in statistical_gates))
    report = {
        "schema_version": 2,
        "candidate_id": "sporttery_handicap_temporal_blend_v2_shadow",
        "mode": "shadow_only",
        "audit": audit,
        "handicaps": list(handicap_values),
        "holdout_seasons": seasons[int(min_train_seasons):],
        "recent_stability_seasons": recent_holdouts,
        "oos_matches": int(predictions["match_id"].nunique()),
        "scenario_rows": int(len(predictions)),
        "bootstrap": bootstrap,
        "gates": gates,
        "statistical_gate_passed": statistical_gate_passed,
        "decision": "shadow_candidate" if statistical_gate_passed else "shadow_rejected",
        "deployment_gate": "blocked_until_time_aligned_sporttery_odds_and_300_settled_shadow_plans",
        "production_change_performed": False,
        "design": {
            "outer_split": "expanding_season_holdout",
            "alpha_selection": "latest_prior_season_only",
            "alpha_grid": list(alpha_grid),
            "max_alpha_by_handicap": max_alpha_map,
            "min_validation_improvement": float(min_validation_improvement),
            "model_c": float(model_c),
        },
    }
    return predictions, folds, {
        "report": report,
        "handicap_summaries": handicap_summaries,
        "league_summaries": league_summary.to_dict(orient="records"),
        "alpha_audit": alpha_audit,
    }
