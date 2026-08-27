from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from evaluate.metrics import compute_metrics, expected_calibration_error


MARGIN_CLASSES = np.arange(-4, 5, dtype=int)
RQSPF_CLASSES = ("H", "D", "A")
DEFAULT_HANDICAPS = (-2, -1, 1, 2)
NUMERIC_FEATURES = (
    "opening_ah_line",
    "ah_home_probability",
    "ah_away_probability",
    "market_home_probability",
    "market_draw_probability",
    "market_away_probability",
    "over_25_probability",
    "under_25_probability",
    "season_progress",
    "month_sin",
    "month_cos",
)
CATEGORICAL_FEATURES = ("league", "opening_ah_line_key")


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _no_vig(*odds: pd.Series) -> tuple[pd.Series, ...]:
    inverse = [1.0 / series.where(series > 1.0) for series in odds]
    denominator = sum(inverse)
    return tuple(series / denominator for series in inverse)


def build_handicap_model_frame(matches: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {
        "match_id", "date", "season", "league", "home_goals", "away_goals",
        "AvgH", "AvgD", "AvgA", "AHh", "AvgAHH", "AvgAHA", "Avg>2.5", "Avg<2.5",
    }
    missing = required - set(matches.columns)
    if missing:
        raise ValueError(f"missing Sporttery handicap model columns: {sorted(missing)}")
    frame = matches.copy()
    for column in ("AvgH", "AvgD", "AvgA", "AHh", "AvgAHH", "AvgAHA", "Avg>2.5", "Avg<2.5", "home_goals", "away_goals"):
        frame[column] = _numeric(frame, column)
    valid = frame[list(required - {"match_id", "date", "season", "league"})].notna().all(axis=1)
    valid &= frame[["AvgH", "AvgD", "AvgA", "AvgAHH", "AvgAHA", "Avg>2.5", "Avg<2.5"]].gt(1.0).all(axis=1)
    frame = frame.loc[valid].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.loc[frame["date"].notna()].copy()
    frame = frame.sort_values(["season", "league", "date", "match_id"], kind="mergesort").reset_index(drop=True)

    market_h, market_d, market_a = _no_vig(frame["AvgH"], frame["AvgD"], frame["AvgA"])
    ah_h, ah_a = _no_vig(frame["AvgAHH"], frame["AvgAHA"])
    over, under = _no_vig(frame["Avg>2.5"], frame["Avg<2.5"])
    frame["opening_ah_line"] = (frame["AHh"] * 4.0).round() / 4.0
    frame["opening_ah_line_key"] = frame["opening_ah_line"].map(lambda value: f"{value:+.2f}")
    frame["ah_home_probability"] = ah_h
    frame["ah_away_probability"] = ah_a
    frame["market_home_probability"] = market_h
    frame["market_draw_probability"] = market_d
    frame["market_away_probability"] = market_a
    frame["over_25_probability"] = over
    frame["under_25_probability"] = under
    group = frame.groupby(["season", "league"], sort=False)
    ordinal = group.cumcount()
    group_size = group["match_id"].transform("size").clip(lower=1)
    frame["season_progress"] = ordinal / group_size
    month = frame["date"].dt.month.astype(float)
    frame["month_sin"] = np.sin(2.0 * np.pi * month / 12.0)
    frame["month_cos"] = np.cos(2.0 * np.pi * month / 12.0)
    frame["actual_margin"] = (frame["home_goals"] - frame["away_goals"]).astype(int)
    frame["margin_class"] = frame["actual_margin"].clip(MARGIN_CLASSES.min(), MARGIN_CLASSES.max()).astype(int)
    audit = {
        "source_rows": int(len(matches)),
        "model_rows": int(len(frame)),
        "rejected_rows": int(len(matches) - len(frame)),
        "seasons": sorted(frame["season"].astype(str).unique().tolist()),
        "leagues": sorted(frame["league"].astype(str).unique().tolist()),
        "feature_count": len(NUMERIC_FEATURES) + len(CATEGORICAL_FEATURES),
        "uses_closing_odds": False,
    }
    return frame, audit


def make_margin_model(*, c: float = 1.0) -> Pipeline:
    transformer = ColumnTransformer(
        [
            ("numeric", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), list(NUMERIC_FEATURES)),
            ("categorical", OneHotEncoder(handle_unknown="ignore"), list(CATEGORICAL_FEATURES)),
        ]
    )
    return Pipeline(
        [
            ("features", transformer),
            ("model", LogisticRegression(C=float(c), max_iter=2000, solver="lbfgs")),
        ]
    )


def fit_final_margin_model(matches: pd.DataFrame, *, c: float = 1.0) -> tuple[Pipeline, dict[str, Any]]:
    frame, audit = build_handicap_model_frame(matches)
    model = make_margin_model(c=c).fit(frame, frame["margin_class"])
    return model, audit


def aligned_margin_probabilities(model: Pipeline, frame: pd.DataFrame) -> np.ndarray:
    predicted = model.predict_proba(frame)
    classes = np.asarray(model.named_steps["model"].classes_, dtype=int)
    aligned = np.zeros((len(frame), len(MARGIN_CLASSES)), dtype=float)
    for source_index, value in enumerate(classes):
        target = np.flatnonzero(MARGIN_CLASSES == value)
        if target.size:
            aligned[:, int(target[0])] = predicted[:, source_index]
    aligned /= aligned.sum(axis=1, keepdims=True)
    return aligned


def margin_to_rqspf_probabilities(margin_probabilities: np.ndarray, handicap: int) -> np.ndarray:
    probabilities = np.asarray(margin_probabilities, dtype=float)
    if probabilities.ndim != 2 or probabilities.shape[1] != len(MARGIN_CLASSES):
        raise ValueError("margin probabilities must have nine columns")
    threshold = -int(handicap)
    return np.column_stack(
        [
            probabilities[:, MARGIN_CLASSES > threshold].sum(axis=1),
            probabilities[:, MARGIN_CLASSES == threshold].sum(axis=1),
            probabilities[:, MARGIN_CLASSES < threshold].sum(axis=1),
        ]
    )


def actual_rqspf_result(actual_margin: object, handicap: int) -> str:
    adjusted = int(actual_margin) + int(handicap)
    return "H" if adjusted > 0 else "D" if adjusted == 0 else "A"


def empirical_line_baseline(
    train: pd.DataFrame,
    test: pd.DataFrame,
    *,
    handicap: int,
    smoothing: float = 20.0,
) -> np.ndarray:
    train_results = train["actual_margin"].map(lambda value: actual_rqspf_result(value, handicap))
    global_counts = train_results.value_counts().reindex(RQSPF_CLASSES, fill_value=0).astype(float)
    global_probability = (global_counts + 1.0) / (global_counts.sum() + len(RQSPF_CLASSES))
    table: dict[str, np.ndarray] = {}
    for key, indices in train.groupby("opening_ah_line_key").groups.items():
        counts = train_results.loc[indices].value_counts().reindex(RQSPF_CLASSES, fill_value=0).astype(float)
        posterior = counts.to_numpy() + float(smoothing) * global_probability.to_numpy()
        table[str(key)] = posterior / posterior.sum()
    return np.vstack([table.get(str(key), global_probability.to_numpy()) for key in test["opening_ah_line_key"]])


def _cluster_bootstrap(differences: pd.Series, *, n_bootstrap: int, random_state: int) -> dict[str, float]:
    values = differences.to_numpy(dtype=float)
    if n_bootstrap < 100:
        raise ValueError("n_bootstrap must be at least 100")
    rng = np.random.default_rng(int(random_state))
    samples = np.empty(int(n_bootstrap), dtype=float)
    for index in range(int(n_bootstrap)):
        draw = rng.integers(0, len(values), size=len(values))
        samples[index] = float(values[draw].mean())
    return {
        "mean_logloss_difference": float(values.mean()),
        "ci95_low": float(np.quantile(samples, 0.025)),
        "ci95_high": float(np.quantile(samples, 0.975)),
        "probability_model_better": float(np.mean(samples < 0.0)),
    }


def run_sporttery_handicap_research(
    matches: pd.DataFrame,
    *,
    handicaps: Iterable[int] = DEFAULT_HANDICAPS,
    min_train_seasons: int = 2,
    model_c: float = 1.0,
    baseline_smoothing: float = 20.0,
    n_bootstrap: int = 2000,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    frame, audit = build_handicap_model_frame(matches)
    seasons = sorted(frame["season"].astype(str).unique().tolist())
    handicap_values = tuple(int(value) for value in handicaps)
    prediction_frames: list[pd.DataFrame] = []
    fold_rows: list[dict[str, Any]] = []
    for holdout_index in range(int(min_train_seasons), len(seasons)):
        holdout = seasons[holdout_index]
        train_seasons = seasons[:holdout_index]
        train = frame.loc[frame["season"].astype(str).isin(train_seasons)].copy()
        test = frame.loc[frame["season"].astype(str).eq(holdout)].copy()
        model = make_margin_model(c=model_c).fit(train, train["margin_class"])
        margin_probability = aligned_margin_probabilities(model, test)
        for handicap in handicap_values:
            model_probability = margin_to_rqspf_probabilities(margin_probability, handicap)
            baseline_probability = empirical_line_baseline(
                train, test, handicap=handicap, smoothing=baseline_smoothing
            )
            truth = test["actual_margin"].map(lambda value: actual_rqspf_result(value, handicap))
            model_metrics = compute_metrics(truth, model_probability)
            baseline_metrics = compute_metrics(truth, baseline_probability)
            fold_rows.append(
                {
                    "holdout_season": holdout,
                    "train_seasons": ",".join(train_seasons),
                    "train_matches": int(len(train)),
                    "test_matches": int(len(test)),
                    "sporttery_handicap": handicap,
                    "model_logloss": model_metrics["logloss"],
                    "baseline_logloss": baseline_metrics["logloss"],
                    "logloss_vs_baseline": model_metrics["logloss"] - baseline_metrics["logloss"],
                    "model_brier": model_metrics["brier"],
                    "baseline_brier": baseline_metrics["brier"],
                    "model_ece": expected_calibration_error(truth, model_probability),
                    "baseline_ece": expected_calibration_error(truth, baseline_probability),
                }
            )
            part = test[["match_id", "date", "season", "league", "home_team", "away_team", "actual_margin", "opening_ah_line"]].copy()
            part["sporttery_handicap"] = handicap
            part["actual_rqspf"] = truth.to_numpy()
            for index, label in enumerate(RQSPF_CLASSES):
                part[f"model_probability_{label.lower()}"] = model_probability[:, index]
                part[f"baseline_probability_{label.lower()}"] = baseline_probability[:, index]
            truth_index = truth.map({"H": 0, "D": 1, "A": 2}).to_numpy(dtype=int)
            row_index = np.arange(len(part))
            part["model_logloss_row"] = -np.log(np.clip(model_probability[row_index, truth_index], 1e-15, 1.0))
            part["baseline_logloss_row"] = -np.log(np.clip(baseline_probability[row_index, truth_index], 1e-15, 1.0))
            prediction_frames.append(part)
    predictions = pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame()
    folds = pd.DataFrame(fold_rows)
    if predictions.empty:
        raise ValueError("no rolling season holdout predictions were produced")
    predictions["logloss_difference"] = predictions["model_logloss_row"] - predictions["baseline_logloss_row"]
    match_difference = predictions.groupby("match_id")["logloss_difference"].mean()
    bootstrap = _cluster_bootstrap(match_difference, n_bootstrap=n_bootstrap, random_state=random_state)
    handicap_summary: list[dict[str, Any]] = []
    for handicap, group in predictions.groupby("sporttery_handicap", sort=True):
        truth = group["actual_rqspf"]
        model_probability = group[["model_probability_h", "model_probability_d", "model_probability_a"]].to_numpy()
        baseline_probability = group[["baseline_probability_h", "baseline_probability_d", "baseline_probability_a"]].to_numpy()
        model_metrics = compute_metrics(truth, model_probability)
        baseline_metrics = compute_metrics(truth, baseline_probability)
        handicap_summary.append(
            {
                "sporttery_handicap": int(handicap),
                "scenario_rows": int(len(group)),
                "model_logloss": model_metrics["logloss"],
                "baseline_logloss": baseline_metrics["logloss"],
                "logloss_vs_baseline": model_metrics["logloss"] - baseline_metrics["logloss"],
                "model_brier": model_metrics["brier"],
                "baseline_brier": baseline_metrics["brier"],
                "model_ece": expected_calibration_error(truth, model_probability),
                "baseline_ece": expected_calibration_error(truth, baseline_probability),
            }
        )
    summaries = pd.DataFrame(handicap_summary)
    league_summary = (
        predictions.groupby("league", sort=True)
        .agg(
            scenario_rows=("match_id", "size"),
            oos_matches=("match_id", "nunique"),
            logloss_vs_baseline=("logloss_difference", "mean"),
        )
        .reset_index()
    )
    holdout_counts = folds.groupby("sporttery_handicap")["logloss_vs_baseline"].agg(
        holdouts="size", better_holdouts=lambda values: int((values < 0.0).sum())
    )
    each_handicap_stable = bool(
        (holdout_counts["better_holdouts"] >= np.minimum(3, holdout_counts["holdouts"])).all()
    )
    recent_holdouts = seasons[-2:]
    recent_folds = folds.loc[folds["holdout_season"].isin(recent_holdouts)]
    recent_stability = bool(
        len(recent_folds) == len(recent_holdouts) * len(handicap_values)
        and (recent_folds["logloss_vs_baseline"] <= 0.0).all()
    )
    gates = {
        "cluster_bootstrap_ci_below_zero": bool(bootstrap["ci95_high"] < 0.0),
        "cluster_bootstrap_probability_at_least_95pct": bool(bootstrap["probability_model_better"] >= 0.95),
        "at_least_three_handicaps_better": bool((summaries["logloss_vs_baseline"] < 0.0).sum() >= 3),
        "each_handicap_better_in_three_holdouts": each_handicap_stable,
        "last_two_holdouts_all_handicaps_not_worse": recent_stability,
        "all_leagues_not_worse": bool((league_summary["logloss_vs_baseline"] <= 0.0).all()),
        "mean_ece_not_worse": bool(summaries["model_ece"].mean() <= summaries["baseline_ece"].mean()),
    }
    statistical_gate_passed = bool(all(gates.values()))
    report = {
        "audit": audit,
        "handicaps": list(handicap_values),
        "holdout_seasons": seasons[int(min_train_seasons):],
        "recent_stability_seasons": recent_holdouts,
        "oos_matches": int(predictions["match_id"].nunique()),
        "scenario_rows": int(len(predictions)),
        "features": list(NUMERIC_FEATURES + CATEGORICAL_FEATURES),
        "bootstrap": bootstrap,
        "gates": gates,
        "statistical_gate_passed": statistical_gate_passed,
        "decision": "research_candidate" if statistical_gate_passed else "research_rejected",
        "deployment_gate": "blocked_until_historical_sporttery_odds_are_time_aligned",
        "production_change_performed": False,
    }
    return predictions, folds, {
        "report": report,
        "handicap_summaries": handicap_summary,
        "league_summaries": league_summary.to_dict(orient="records"),
    }
