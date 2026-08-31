from __future__ import annotations

import math

import numpy as np
import pandas as pd

from evaluate.bootstrap import paired_bootstrap_logloss_difference
from evaluate.metrics import compute_metrics, expected_calibration_error
from world_cup.calibration import fit_timeline_calibrator, predict_calibrated_match
from world_cup.model import WorldCupBaselineModel


def evaluate_tournament_holdouts(
    matches: pd.DataFrame,
    *,
    min_train_tournaments: int = 2,
) -> pd.DataFrame:
    years = sorted(matches["tournament_year"].astype(int).unique())
    rows = []
    for index in range(min_train_tournaments, len(years)):
        holdout = years[index]
        train = matches[matches["tournament_year"].astype(int).isin(years[:index])]
        test = matches[matches["tournament_year"].astype(int).eq(holdout)]
        model = WorldCupBaselineModel().fit(train)
        predictions = [
            model.predict_match(row.home_team, row.away_team)
            for row in test.itertuples(index=False)
        ]
        proba = pd.DataFrame(predictions)[["p_home", "p_draw", "p_away"]]
        metrics = compute_metrics(test["actual_result"], proba)
        uniform_proba = pd.DataFrame(
            np.full((len(test), 3), 1.0 / 3.0),
            columns=["p_home", "p_draw", "p_away"],
        )
        uniform_metrics = compute_metrics(test["actual_result"], uniform_proba)
        rows.append(
            {
                "holdout_year": int(holdout),
                "train_years": ",".join(str(year) for year in years[:index]),
                "train_size": int(len(train)),
                "test_size": int(len(test)),
                "brier": float(metrics["brier"]),
                "logloss": float(metrics["logloss"]),
                "uniform_brier": float(uniform_metrics["brier"]),
                "uniform_logloss": float(uniform_metrics["logloss"]),
                "logloss_vs_uniform": float(metrics["logloss"] - uniform_metrics["logloss"]),
                "beats_uniform": bool(metrics["logloss"] < math.log(3.0)),
            }
        )
    return pd.DataFrame(rows)


def evaluate_international_timeline_holdouts(
    matches: pd.DataFrame,
    *,
    holdout_years: tuple[int, ...] = (2010, 2014, 2018, 2022),
    history_start: str = "2000-01-01",
    model_kwargs: dict[str, object] | None = None,
) -> pd.DataFrame:
    model_kwargs = dict(model_kwargs or {})
    data = matches[matches["date"] >= pd.Timestamp(history_start)].copy()
    rows = []
    for holdout_year in holdout_years:
        tournament = data[
            data["tournament"].astype(str).eq("FIFA World Cup")
            & data["date"].dt.year.eq(int(holdout_year))
        ].copy()
        if tournament.empty:
            continue
        start = tournament["date"].min()
        train = data[data["date"] < start].copy()
        model = WorldCupBaselineModel(**model_kwargs).fit(train)
        predictions = [
            model.predict_match(
                row.home_team,
                row.away_team,
                neutral=bool(row.neutral),
            )
            for row in tournament.itertuples(index=False)
        ]
        proba = pd.DataFrame(predictions)[["p_home", "p_draw", "p_away"]]
        metrics = compute_metrics(tournament["actual_result"], proba)
        actual_indices = tournament["actual_result"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
        predicted_indices = proba.to_numpy().argmax(axis=1)
        draw_mask = actual_indices == 1
        accuracy = float(np.mean(predicted_indices == actual_indices))
        draw_recall = (
            float(np.mean(predicted_indices[draw_mask] == 1))
            if np.any(draw_mask)
            else float("nan")
        )
        uniform = pd.DataFrame(
            np.full((len(tournament), 3), 1.0 / 3.0),
            columns=["p_home", "p_draw", "p_away"],
        )
        uniform_metrics = compute_metrics(tournament["actual_result"], uniform)
        rows.append(
            {
                "holdout_year": int(holdout_year),
                "train_end": str((start - pd.Timedelta(days=1)).date()),
                "train_size": int(len(train)),
                "test_size": int(len(tournament)),
                "brier": float(metrics["brier"]),
                "logloss": float(metrics["logloss"]),
                "accuracy": accuracy,
                "draw_recall": draw_recall,
                "ece": expected_calibration_error(actual_indices, proba),
                "uniform_logloss": float(uniform_metrics["logloss"]),
                "logloss_vs_uniform": float(metrics["logloss"] - uniform_metrics["logloss"]),
                "beats_uniform": bool(metrics["logloss"] < uniform_metrics["logloss"]),
            }
        )
    return pd.DataFrame(rows)


def compare_international_models(
    matches: pd.DataFrame,
    *,
    holdout_years: tuple[int, ...] = (2010, 2014, 2018, 2022),
    draw_correlations: tuple[float, ...] = (0.0, -0.05, -0.10, -0.15),
) -> pd.DataFrame:
    frames = []
    for correlation in draw_correlations:
        result = evaluate_international_timeline_holdouts(
            matches,
            holdout_years=holdout_years,
            model_kwargs={"draw_correlation": correlation},
        )
        result.insert(0, "draw_correlation", correlation)
        result.insert(
            0,
            "model",
            "elo_poisson" if correlation == 0.0 else "elo_dixon_coles",
        )
        frames.append(result)
    return pd.concat(frames, ignore_index=True)


def evaluate_calibrated_timeline_holdouts(
    matches: pd.DataFrame,
    *,
    holdout_years: tuple[int, ...] = (2010, 2014, 2018, 2022),
    history_start: str = "2000-01-01",
    calibration_years: int = 8,
    c: float = 0.3,
) -> pd.DataFrame:
    data = matches[matches["date"] >= pd.Timestamp(history_start)].copy()
    rows = []
    for holdout_year in holdout_years:
        tournament = data[
            data["tournament"].astype(str).eq("FIFA World Cup")
            & data["date"].dt.year.eq(int(holdout_year))
        ].copy()
        if tournament.empty:
            continue
        start = tournament["date"].min()
        train = data[data["date"] < start].copy()
        calibration_start = start - pd.DateOffset(years=calibration_years)
        baseline, calibrator, calibration_size = fit_timeline_calibrator(
            train,
            calibration_start=calibration_start,
            c=c,
        )
        predictions = [
            predict_calibrated_match(
                baseline,
                calibrator,
                row.home_team,
                row.away_team,
                neutral=bool(row.neutral),
                importance=float(row.importance),
            )
            for row in tournament.itertuples(index=False)
        ]
        proba = pd.DataFrame(predictions)[["p_home", "p_draw", "p_away"]]
        metrics = compute_metrics(tournament["actual_result"], proba)
        actual_indices = tournament["actual_result"].map({"H": 0, "D": 1, "A": 2}).to_numpy()
        predicted_indices = proba.to_numpy().argmax(axis=1)
        draw_mask = actual_indices == 1
        rows.append(
            {
                "model": "multinomial_calibrator",
                "calibration_years": int(calibration_years),
                "c": float(c),
                "holdout_year": int(holdout_year),
                "train_end": str((start - pd.Timedelta(days=1)).date()),
                "train_size": int(len(train)),
                "calibration_size": int(calibration_size),
                "test_size": int(len(tournament)),
                "brier": float(metrics["brier"]),
                "logloss": float(metrics["logloss"]),
                "accuracy": float(np.mean(predicted_indices == actual_indices)),
                "draw_recall": (
                    float(np.mean(predicted_indices[draw_mask] == 1))
                    if np.any(draw_mask)
                    else float("nan")
                ),
                "ece": expected_calibration_error(actual_indices, proba),
            }
        )
    return pd.DataFrame(rows)


def compare_calibration_windows(
    matches: pd.DataFrame,
    *,
    calibration_windows: tuple[int, ...] = (4, 8, 12),
    c: float = 0.3,
) -> pd.DataFrame:
    frames = [
        evaluate_calibrated_timeline_holdouts(
            matches,
            calibration_years=years,
            c=c,
        )
        for years in calibration_windows
    ]
    return pd.concat(frames, ignore_index=True)


def bootstrap_calibrator_vs_baseline(
    matches: pd.DataFrame,
    *,
    holdout_years: tuple[int, ...] = (2018, 2022),
    calibration_years: int = 4,
    c: float = 0.3,
    n_bootstrap: int = 5_000,
) -> dict[str, object]:
    data = matches[matches["date"] >= pd.Timestamp("2000-01-01")].copy()
    actual: list[str] = []
    calibrated_probabilities: list[list[float]] = []
    baseline_probabilities: list[list[float]] = []

    for holdout_year in holdout_years:
        tournament = data[
            data["tournament"].astype(str).eq("FIFA World Cup")
            & data["date"].dt.year.eq(int(holdout_year))
        ].copy()
        start = tournament["date"].min()
        train = data[data["date"] < start].copy()
        baseline, calibrator, _ = fit_timeline_calibrator(
            train,
            calibration_start=start - pd.DateOffset(years=calibration_years),
            c=c,
        )
        for row in tournament.itertuples(index=False):
            raw = baseline.predict_match(
                row.home_team,
                row.away_team,
                neutral=bool(row.neutral),
            )
            calibrated = predict_calibrated_match(
                baseline,
                calibrator,
                row.home_team,
                row.away_team,
                neutral=bool(row.neutral),
                importance=float(row.importance),
            )
            actual.append(str(row.actual_result))
            baseline_probabilities.append(
                [float(raw["p_home"]), float(raw["p_draw"]), float(raw["p_away"])]
            )
            calibrated_probabilities.append(
                [
                    float(calibrated["p_home"]),
                    float(calibrated["p_draw"]),
                    float(calibrated["p_away"]),
                ]
            )

    result = paired_bootstrap_logloss_difference(
        actual,
        calibrated_probabilities,
        baseline_probabilities,
        n_bootstrap=n_bootstrap,
        random_state=42,
    )
    return {
        "holdout_years": list(holdout_years),
        "matches": len(actual),
        "calibration_years": calibration_years,
        "c": c,
        **result,
    }
