from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from evaluate.metrics import compute_metrics, expected_calibration_error
from evaluate.sporttery_handicap_model import (
    DEFAULT_HANDICAPS,
    MARGIN_CLASSES,
    NUMERIC_FEATURES,
    CATEGORICAL_FEATURES,
    RQSPF_CLASSES,
    _cluster_bootstrap,
    actual_rqspf_result,
    aligned_margin_probabilities,
    build_handicap_model_frame,
    empirical_line_baseline,
    make_margin_model,
    margin_to_rqspf_probabilities,
)
from evaluate.sporttery_handicap_shadow_v2 import (
    DEFAULT_ALPHA_GRID,
    DEFAULT_MAX_ALPHA,
    _select_temporal_alpha,
    blend_probabilities,
)


MOVEMENT_NUMERIC_FEATURES = (
    "closing_ah_line",
    "home_line_strength_delta",
    "closing_ah_home_probability",
    "closing_ah_away_probability",
    "ah_home_probability_delta",
    "closing_market_home_probability",
    "closing_market_draw_probability",
    "closing_market_away_probability",
    "market_home_probability_delta",
    "closing_over_25_probability",
    "closing_under_25_probability",
    "over_25_probability_delta",
    "favorite_hot_without_line_support",
    "line_upgrade_without_price_support",
    "line_downgrade",
)
MOVEMENT_CATEGORICAL_FEATURES = ("closing_ah_line_key", "line_movement_bucket")
ALL_MOVEMENT_NUMERIC_FEATURES = NUMERIC_FEATURES + MOVEMENT_NUMERIC_FEATURES
ALL_MOVEMENT_CATEGORICAL_FEATURES = CATEGORICAL_FEATURES + MOVEMENT_CATEGORICAL_FEATURES
DEFAULT_BETA_GRID = (0.0, 0.10, 0.25, 0.50)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _no_vig(*odds: pd.Series) -> tuple[pd.Series, ...]:
    inverse = [1.0 / item.where(item > 1.0) for item in odds]
    denominator = sum(inverse)
    return tuple(item / denominator for item in inverse)


def _movement_bucket(value: float) -> str:
    if value >= 0.50:
        return "home_upgrade_2plus"
    if value >= 0.25:
        return "home_upgrade_quarter"
    if value <= -0.50:
        return "home_downgrade_2plus"
    if value <= -0.25:
        return "home_downgrade_quarter"
    return "stable"


def build_movement_model_frame(matches: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame, base_audit = build_handicap_model_frame(matches)
    required = (
        "AHCh", "AvgCAHH", "AvgCAHA", "AvgCH", "AvgCD", "AvgCA",
        "AvgC>2.5", "AvgC<2.5",
    )
    for column in required:
        frame[column] = _numeric(frame, column)
    valid = frame[list(required)].notna().all(axis=1)
    valid &= frame[["AvgCAHH", "AvgCAHA", "AvgCH", "AvgCD", "AvgCA", "AvgC>2.5", "AvgC<2.5"]].gt(1.0).all(axis=1)
    movement = frame.loc[valid].copy()

    close_ah_h, close_ah_a = _no_vig(movement["AvgCAHH"], movement["AvgCAHA"])
    close_h, close_d, close_a = _no_vig(movement["AvgCH"], movement["AvgCD"], movement["AvgCA"])
    close_over, close_under = _no_vig(movement["AvgC>2.5"], movement["AvgC<2.5"])
    movement["closing_ah_line"] = (movement["AHCh"] * 4.0).round() / 4.0
    movement["closing_ah_line_key"] = movement["closing_ah_line"].map(lambda value: f"{value:+.2f}")
    # More negative means a stronger home handicap: -0.75 -> -1.00 is +0.25.
    movement["home_line_strength_delta"] = movement["opening_ah_line"] - movement["closing_ah_line"]
    movement["closing_ah_home_probability"] = close_ah_h
    movement["closing_ah_away_probability"] = close_ah_a
    movement["ah_home_probability_delta"] = close_ah_h - movement["ah_home_probability"]
    movement["closing_market_home_probability"] = close_h
    movement["closing_market_draw_probability"] = close_d
    movement["closing_market_away_probability"] = close_a
    movement["market_home_probability_delta"] = close_h - movement["market_home_probability"]
    movement["closing_over_25_probability"] = close_over
    movement["closing_under_25_probability"] = close_under
    movement["over_25_probability_delta"] = close_over - movement["over_25_probability"]
    movement["favorite_hot_without_line_support"] = (
        (movement["market_home_probability_delta"] >= 0.03)
        & (movement["home_line_strength_delta"] < 0.125)
    ).astype(float)
    movement["line_upgrade_without_price_support"] = (
        (movement["home_line_strength_delta"] >= 0.25)
        & (movement["ah_home_probability_delta"] <= 0.0)
    ).astype(float)
    movement["line_downgrade"] = (movement["home_line_strength_delta"] <= -0.25).astype(float)
    movement["line_movement_bucket"] = movement["home_line_strength_delta"].map(_movement_bucket)

    audit = {
        **base_audit,
        "base_model_rows": int(len(frame)),
        "movement_model_rows": int(len(movement)),
        "movement_rejected_rows": int(len(frame) - len(movement)),
        "movement_feature_count": len(ALL_MOVEMENT_NUMERIC_FEATURES) + len(ALL_MOVEMENT_CATEGORICAL_FEATURES),
        "uses_opening_odds": True,
        "uses_pregame_closing_proxy": True,
        "uses_post_kickoff_data": False,
        "line_movement_speed_available_in_historical_proxy": False,
    }
    return movement.reset_index(drop=True), audit


def make_movement_margin_model(*, c: float = 0.5) -> Pipeline:
    transformer = ColumnTransformer(
        [
            (
                "numeric",
                Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]),
                list(ALL_MOVEMENT_NUMERIC_FEATURES),
            ),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore"),
                list(ALL_MOVEMENT_CATEGORICAL_FEATURES),
            ),
        ]
    )
    return Pipeline(
        [
            ("features", transformer),
            ("model", LogisticRegression(C=float(c), max_iter=2000, solver="lbfgs")),
        ]
    )


def margin_category_probabilities(probabilities: np.ndarray) -> dict[str, np.ndarray]:
    values = np.asarray(probabilities, dtype=float)
    return {
        "home_not_win": values[:, MARGIN_CLASSES <= 0].sum(axis=1),
        "home_win": values[:, MARGIN_CLASSES >= 1].sum(axis=1),
        "home_win_exactly_1": values[:, MARGIN_CLASSES == 1].sum(axis=1),
        "home_win_2_plus": values[:, MARGIN_CLASSES >= 2].sum(axis=1),
    }


def _select_movement_beta(
    train: pd.DataFrame,
    *,
    handicap: int,
    alpha_grid: Sequence[float],
    max_alpha: float,
    beta_grid: Sequence[float],
    max_beta: float,
    model_c: float,
    baseline_smoothing: float,
    min_validation_improvement: float,
    max_validation_ece_degradation: float,
) -> tuple[float, dict[str, Any]]:
    seasons = sorted(train["season"].astype(str).unique().tolist())
    if len(seasons) < 2:
        return 0.0, {"reason": "insufficient_inner_seasons"}
    validation_season = seasons[-1]
    inner = train[train["season"].astype(str).isin(seasons[:-1])].copy()
    validation = train[train["season"].astype(str).eq(validation_season)].copy()
    if inner.empty or validation.empty:
        return 0.0, {"reason": "insufficient_inner_rows"}

    alpha, alpha_audit = _select_temporal_alpha(
        train,
        handicap=handicap,
        alpha_grid=alpha_grid,
        max_alpha=max_alpha,
        model_c=model_c,
        baseline_smoothing=baseline_smoothing,
        min_validation_improvement=min_validation_improvement,
    )
    opening_model = make_margin_model(c=model_c).fit(inner, inner["margin_class"])
    movement_model = make_movement_margin_model(c=model_c).fit(inner, inner["margin_class"])
    opening_probability = margin_to_rqspf_probabilities(
        aligned_margin_probabilities(opening_model, validation), handicap
    )
    movement_probability = margin_to_rqspf_probabilities(
        aligned_margin_probabilities(movement_model, validation), handicap
    )
    baseline_probability = empirical_line_baseline(
        inner, validation, handicap=handicap, smoothing=baseline_smoothing
    )
    v2_probability = blend_probabilities(baseline_probability, opening_probability, alpha)
    truth = validation["actual_margin"].map(lambda value: actual_rqspf_result(value, handicap))
    v2_logloss = compute_metrics(truth, v2_probability)["logloss"]
    v2_ece = expected_calibration_error(truth, v2_probability)
    allowed = sorted({float(value) for value in beta_grid if 0.0 <= float(value) <= float(max_beta)} | {0.0})
    trials: list[dict[str, float]] = []
    for beta in allowed:
        candidate = blend_probabilities(v2_probability, movement_probability, beta)
        trials.append(
            {
                "beta": beta,
                "logloss": compute_metrics(truth, candidate)["logloss"],
                "ece": expected_calibration_error(truth, candidate),
            }
        )
    eligible = [
        row
        for row in trials
        if v2_logloss - row["logloss"] >= float(min_validation_improvement)
        and row["ece"] <= v2_ece + float(max_validation_ece_degradation)
    ]
    best = min(eligible, key=lambda row: (row["logloss"], row["ece"], row["beta"])) if eligible else trials[0]
    improvement = float(v2_logloss - best["logloss"])
    selected = float(best["beta"]) if eligible else 0.0
    return selected, {
        "reason": "selected" if selected > 0 else "v2_fallback",
        "validation_season": validation_season,
        "validation_matches": int(len(validation)),
        "selected_v2_alpha": alpha,
        "v2_alpha_audit": alpha_audit,
        "v2_logloss": float(v2_logloss),
        "v2_ece": float(v2_ece),
        "best_logloss": float(best["logloss"]),
        "validation_improvement": improvement,
        "selected_beta": selected,
        "trials": trials,
    }


def run_handicap_margin_movement_v3(
    matches: pd.DataFrame,
    *,
    handicaps: Iterable[int] = DEFAULT_HANDICAPS,
    min_train_seasons: int = 2,
    model_c: float = 0.5,
    baseline_smoothing: float = 20.0,
    alpha_grid: Sequence[float] = DEFAULT_ALPHA_GRID,
    max_alpha_by_handicap: Mapping[int, float] | None = None,
    beta_grid: Sequence[float] = DEFAULT_BETA_GRID,
    max_beta_by_handicap: Mapping[int, float] | None = None,
    min_validation_improvement: float = 0.0005,
    max_validation_ece_degradation: float = 0.0005,
    n_bootstrap: int = 2000,
    random_state: int = 42,
    time_aligned_events: int = 0,
    required_time_aligned_events: int = 300,
    settled_shadow_plans: int = 0,
    required_settled_shadow_plans: int = 300,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    frame, audit = build_movement_model_frame(matches)
    seasons = sorted(frame["season"].astype(str).unique().tolist())
    handicap_values = tuple(int(value) for value in handicaps)
    max_alpha = dict(DEFAULT_MAX_ALPHA)
    if max_alpha_by_handicap:
        max_alpha.update({int(key): float(value) for key, value in max_alpha_by_handicap.items()})
    max_beta = {-2: 0.50, -1: 0.50, 1: 0.25, 2: 0.25}
    if max_beta_by_handicap:
        max_beta.update({int(key): float(value) for key, value in max_beta_by_handicap.items()})

    parts: list[pd.DataFrame] = []
    fold_rows: list[dict[str, Any]] = []
    selection_audit: list[dict[str, Any]] = []
    for holdout_index in range(int(min_train_seasons), len(seasons)):
        holdout = seasons[holdout_index]
        train_seasons = seasons[:holdout_index]
        train = frame[frame["season"].astype(str).isin(train_seasons)].copy()
        test = frame[frame["season"].astype(str).eq(holdout)].copy()
        opening_model = make_margin_model(c=model_c).fit(train, train["margin_class"])
        movement_model = make_movement_margin_model(c=model_c).fit(train, train["margin_class"])
        opening_margin = aligned_margin_probabilities(opening_model, test)
        movement_margin = aligned_margin_probabilities(movement_model, test)
        categories = margin_category_probabilities(movement_margin)
        for handicap in handicap_values:
            alpha, alpha_audit = _select_temporal_alpha(
                train,
                handicap=handicap,
                alpha_grid=alpha_grid,
                max_alpha=max_alpha.get(handicap, 0.0),
                model_c=model_c,
                baseline_smoothing=baseline_smoothing,
                min_validation_improvement=min_validation_improvement,
            )
            beta, beta_audit = _select_movement_beta(
                train,
                handicap=handicap,
                alpha_grid=alpha_grid,
                max_alpha=max_alpha.get(handicap, 0.0),
                beta_grid=beta_grid,
                max_beta=max_beta.get(handicap, 0.0),
                model_c=model_c,
                baseline_smoothing=baseline_smoothing,
                min_validation_improvement=min_validation_improvement,
                max_validation_ece_degradation=max_validation_ece_degradation,
            )
            selection_audit.append(
                {
                    "holdout_season": holdout,
                    "sporttery_handicap": handicap,
                    "selected_v2_alpha": alpha,
                    "v2_alpha_audit": alpha_audit,
                    **beta_audit,
                }
            )
            baseline = empirical_line_baseline(
                train, test, handicap=handicap, smoothing=baseline_smoothing
            )
            opening_rqspf = margin_to_rqspf_probabilities(opening_margin, handicap)
            movement_rqspf = margin_to_rqspf_probabilities(movement_margin, handicap)
            v2 = blend_probabilities(baseline, opening_rqspf, alpha)
            v3 = blend_probabilities(v2, movement_rqspf, beta)
            truth = test["actual_margin"].map(lambda value: actual_rqspf_result(value, handicap))
            v2_metrics = compute_metrics(truth, v2)
            v3_metrics = compute_metrics(truth, v3)
            fold_rows.append(
                {
                    "holdout_season": holdout,
                    "train_seasons": ",".join(train_seasons),
                    "train_matches": int(len(train)),
                    "test_matches": int(len(test)),
                    "sporttery_handicap": handicap,
                    "selected_v2_alpha": alpha,
                    "selected_v3_beta": beta,
                    "v3_logloss": v3_metrics["logloss"],
                    "v2_logloss": v2_metrics["logloss"],
                    "logloss_vs_v2": v3_metrics["logloss"] - v2_metrics["logloss"],
                    "v3_brier": v3_metrics["brier"],
                    "v2_brier": v2_metrics["brier"],
                    "v3_ece": expected_calibration_error(truth, v3),
                    "v2_ece": expected_calibration_error(truth, v2),
                }
            )
            part = test[
                [
                    "match_id", "date", "season", "league", "home_team", "away_team",
                    "actual_margin", "opening_ah_line", "closing_ah_line",
                    "home_line_strength_delta", "ah_home_probability_delta",
                    "market_home_probability_delta", "line_movement_bucket",
                ]
            ].copy()
            part["sporttery_handicap"] = handicap
            part["actual_rqspf"] = truth.to_numpy()
            part["selected_v2_alpha"] = alpha
            part["selected_v3_beta"] = beta
            for index, label in enumerate(RQSPF_CLASSES):
                part[f"v3_probability_{label.lower()}"] = v3[:, index]
                part[f"v2_probability_{label.lower()}"] = v2[:, index]
            for name, values in categories.items():
                part[f"margin_probability_{name}"] = values
            truth_index = truth.map({"H": 0, "D": 1, "A": 2}).to_numpy(dtype=int)
            indices = np.arange(len(part))
            part["v3_logloss_row"] = -np.log(np.clip(v3[indices, truth_index], 1e-15, 1.0))
            part["v2_logloss_row"] = -np.log(np.clip(v2[indices, truth_index], 1e-15, 1.0))
            parts.append(part)

    predictions = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    folds = pd.DataFrame(fold_rows)
    if predictions.empty:
        raise ValueError("no v3 rolling holdout predictions were produced")
    predictions["logloss_difference"] = predictions["v3_logloss_row"] - predictions["v2_logloss_row"]
    bootstrap = _cluster_bootstrap(
        predictions.groupby("match_id")["logloss_difference"].mean(),
        n_bootstrap=n_bootstrap,
        random_state=random_state,
    )

    summaries: list[dict[str, Any]] = []
    for handicap, group in predictions.groupby("sporttery_handicap", sort=True):
        truth = group["actual_rqspf"]
        v3 = group[["v3_probability_h", "v3_probability_d", "v3_probability_a"]].to_numpy()
        v2 = group[["v2_probability_h", "v2_probability_d", "v2_probability_a"]].to_numpy()
        v3_metrics = compute_metrics(truth, v3)
        v2_metrics = compute_metrics(truth, v2)
        summaries.append(
            {
                "sporttery_handicap": int(handicap),
                "scenario_rows": int(len(group)),
                "v3_logloss": v3_metrics["logloss"],
                "v2_logloss": v2_metrics["logloss"],
                "logloss_vs_v2": v3_metrics["logloss"] - v2_metrics["logloss"],
                "v3_brier": v3_metrics["brier"],
                "v2_brier": v2_metrics["brier"],
                "v3_ece": expected_calibration_error(truth, v3),
                "v2_ece": expected_calibration_error(truth, v2),
            }
        )
    summary_frame = pd.DataFrame(summaries)
    league_summary = (
        predictions.groupby("league", sort=True)
        .agg(
            scenario_rows=("match_id", "size"),
            oos_matches=("match_id", "nunique"),
            logloss_vs_v2=("logloss_difference", "mean"),
        )
        .reset_index()
    )
    recent = seasons[-2:]
    recent_folds = folds[folds["holdout_season"].isin(recent)]
    statistical_gates = {
        "bootstrap_ci_below_zero_vs_v2": bool(bootstrap["ci95_high"] < 0.0),
        "bootstrap_probability_better_at_least_95pct": bool(bootstrap["probability_model_better"] >= 0.95),
        "last_two_holdouts_all_handicaps_not_worse": bool(
            len(recent_folds) == len(recent) * len(handicap_values)
            and (recent_folds["logloss_vs_v2"] <= 0.0).all()
        ),
        "all_leagues_not_worse": bool((league_summary["logloss_vs_v2"] <= 0.0).all()),
        "mean_brier_not_worse": bool(summary_frame["v3_brier"].mean() <= summary_frame["v2_brier"].mean()),
        "mean_ece_not_worse": bool(summary_frame["v3_ece"].mean() <= summary_frame["v2_ece"].mean()),
    }
    production_gates = {
        "historical_proxy_statistical_gate": bool(all(statistical_gates.values())),
        "time_aligned_sporttery_events_at_least_300": int(time_aligned_events) >= int(required_time_aligned_events),
        "settled_shadow_plans_at_least_300": int(settled_shadow_plans) >= int(required_settled_shadow_plans),
        "sporttery_rqspf_roi_backtest_available": False,
        "risk_adjusted_return_not_worse": False,
        "max_drawdown_not_worse": False,
    }
    statistical_passed = bool(all(statistical_gates.values()))
    production_allowed = bool(all(production_gates.values()))
    report = {
        "schema_version": 1,
        "candidate_id": "handicap_margin_movement_v3_shadow",
        "mode": "shadow_only",
        "audit": audit,
        "oos_matches": int(predictions["match_id"].nunique()),
        "scenario_rows": int(len(predictions)),
        "holdout_seasons": seasons[int(min_train_seasons):],
        "recent_stability_seasons": recent,
        "bootstrap_vs_v2": bootstrap,
        "statistical_gates": statistical_gates,
        "production_gates": production_gates,
        "time_aligned_sporttery_events": int(time_aligned_events),
        "required_time_aligned_sporttery_events": int(required_time_aligned_events),
        "settled_shadow_plans": int(settled_shadow_plans),
        "required_settled_shadow_plans": int(required_settled_shadow_plans),
        "statistical_gate_passed": statistical_passed,
        "decision": "shadow_candidate" if statistical_passed else "shadow_rejected",
        "production_promotion_allowed": production_allowed,
        "production_change_performed": False,
        "deployment_gate": (
            "eligible_for_controlled_production_review"
            if production_allowed
            else "blocked_until_time_aligned_sporttery_samples_roi_and_drawdown_gates_pass"
        ),
        "design": {
            "historical_proxy": "football-data.co.uk opening and pregame closing multi-bookmaker averages",
            "outer_split": "expanding_season_holdout",
            "inner_selection": "latest_prior_season_only",
            "candidate_comparison": "v3 movement blend versus current v2 temporal blend",
            "uses_post_kickoff_data": False,
            "can_trigger_bet_alone": False,
            "can_write_production_ledger": False,
        },
    }
    return predictions, folds, {
        "report": report,
        "handicap_summaries": summaries,
        "league_summaries": league_summary.to_dict(orient="records"),
        "selection_audit": selection_audit,
    }
