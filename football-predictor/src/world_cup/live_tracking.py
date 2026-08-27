from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from world_cup.data import normalize_national_team


RESULT_ORDER = ("H", "D", "A")


def load_result_overrides(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    if not source.exists():
        return pd.DataFrame()
    frame = pd.read_csv(source)
    required = {"date", "home_team", "away_team", "home_goals", "away_goals"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing result override columns: {sorted(missing)}")
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame["home_team"] = frame["home_team"].map(normalize_national_team)
    frame["away_team"] = frame["away_team"].map(normalize_national_team)
    frame["home_goals"] = pd.to_numeric(frame["home_goals"], errors="raise").astype(int)
    frame["away_goals"] = pd.to_numeric(frame["away_goals"], errors="raise").astype(int)
    return frame


def combine_completed_results(
    international_results: pd.DataFrame,
    overrides: pd.DataFrame | None = None,
) -> pd.DataFrame:
    columns = [
        "date",
        "home_team",
        "away_team",
        "home_goals",
        "away_goals",
        "actual_result",
        "tournament",
        "result_source",
        "source_url",
    ]
    completed = international_results[
        international_results["home_goals"].notna()
        & international_results["away_goals"].notna()
    ].copy()
    completed["result_source"] = "international_results"
    completed["source_url"] = ""

    if overrides is not None and not overrides.empty:
        manual = overrides.copy()
        manual["actual_result"] = np.where(
            manual["home_goals"] > manual["away_goals"],
            "H",
            np.where(manual["home_goals"] < manual["away_goals"], "A", "D"),
        )
        if "result_source" not in manual:
            manual["result_source"] = "manual_verified"
        if "source_url" not in manual:
            manual["source_url"] = ""
        if "tournament" not in manual:
            manual["tournament"] = "FIFA World Cup"
        keys = ["date", "home_team", "away_team"]
        override_keys = pd.MultiIndex.from_frame(manual[keys])
        completed_keys = pd.MultiIndex.from_frame(completed[keys])
        completed = completed[~completed_keys.isin(override_keys)]
        completed = pd.concat([completed, manual], ignore_index=True, sort=False)

    return completed[columns].sort_values(
        ["date", "home_team", "away_team"],
        kind="mergesort",
    ).reset_index(drop=True)


def load_prediction_files(path: str | Path) -> pd.DataFrame:
    root = Path(path)
    frames = []
    for file in sorted(root.glob("world_cup_????-??-??*.csv")):
        frame = pd.read_csv(file)
        required = {
            "date",
            "home_team",
            "away_team",
            "p_home",
            "p_draw",
            "p_away",
        }
        if required - set(frame.columns):
            continue
        frame["prediction_file"] = file.name
        frame["model_variant"] = (
            "calibrated" if "_calibrated" in file.stem else "baseline"
        )
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    predictions = pd.concat(frames, ignore_index=True)
    predictions["date"] = pd.to_datetime(predictions["date"], errors="raise")
    predictions["home_team"] = predictions["home_team"].map(normalize_national_team)
    predictions["away_team"] = predictions["away_team"].map(normalize_national_team)
    return predictions


def settle_predictions(
    predictions: pd.DataFrame,
    completed_results: pd.DataFrame,
) -> pd.DataFrame:
    keys = ["date", "home_team", "away_team"]
    results = completed_results.copy()
    if "tournament" in results.columns:
        results = results[results["tournament"].astype(str).eq("FIFA World Cup")]
    results = results.drop_duplicates(keys, keep="last")
    settled = predictions.merge(
        results,
        on=keys,
        how="left",
        validate="many_to_one",
    )
    settled["settled"] = settled["actual_result"].notna()
    settled["predicted_result"] = settled[["p_home", "p_draw", "p_away"]].idxmax(axis=1)
    settled["predicted_result"] = settled["predicted_result"].map(
        {"p_home": "H", "p_draw": "D", "p_away": "A"}
    )
    settled["correct"] = (
        settled["predicted_result"].eq(settled["actual_result"])
        & settled["settled"]
    )
    settled["actual_probability"] = np.nan
    for result, column in zip(RESULT_ORDER, ("p_home", "p_draw", "p_away")):
        mask = settled["actual_result"].eq(result)
        settled.loc[mask, "actual_probability"] = settled.loc[mask, column]
    settled["logloss"] = np.where(
        settled["settled"],
        -np.log(settled["actual_probability"].clip(lower=1e-15)),
        np.nan,
    )
    settled["brier"] = np.nan
    for index, row in settled[settled["settled"]].iterrows():
        target = np.array([row["actual_result"] == value for value in RESULT_ORDER], dtype=float)
        probability = np.array([row["p_home"], row["p_draw"], row["p_away"]], dtype=float)
        settled.loc[index, "brier"] = float(np.sum((probability - target) ** 2))
    settled["actual_total_goals"] = settled["home_goals"] + settled["away_goals"]
    settled["expected_total_goals"] = (
        settled.get("expected_home_goals", np.nan)
        + settled.get("expected_away_goals", np.nan)
    )
    settled["exact_score"] = (
        settled.get("most_likely_home_goals", np.nan).eq(settled["home_goals"])
        & settled.get("most_likely_away_goals", np.nan).eq(settled["away_goals"])
        & settled["settled"]
    )
    return settled


def summarize_settled_predictions(settled: pd.DataFrame) -> dict[str, object]:
    completed = settled[settled["settled"]].copy()
    if completed.empty:
        return {
            "settled_matches": 0,
            "pending_predictions": int((~settled["settled"]).sum()),
        }
    return {
        "settled_matches": int(len(completed)),
        "pending_predictions": int((~settled["settled"]).sum()),
        "accuracy": float(completed["correct"].mean()),
        "exact_score_accuracy": float(completed["exact_score"].mean()),
        "mean_logloss": float(completed["logloss"].mean()),
        "uniform_logloss": math.log(3.0),
        "mean_brier": float(completed["brier"].mean()),
        "expected_goals": float(completed["expected_total_goals"].sum()),
        "actual_goals": int(completed["actual_total_goals"].sum()),
        "goal_ratio_actual_to_expected": float(
            completed["actual_total_goals"].sum()
            / completed["expected_total_goals"].sum()
        ),
    }


def goal_environment_report(
    completed_results: pd.DataFrame,
    *,
    current_year: int = 2026,
    historical_years: tuple[int, ...] = (2010, 2014, 2018, 2022),
) -> dict[str, object]:
    world_cups = completed_results[
        completed_results["tournament"].astype(str).eq("FIFA World Cup")
    ].copy()
    current = world_cups[world_cups["date"].dt.year.eq(current_year)]
    historical = world_cups[world_cups["date"].dt.year.isin(historical_years)]
    current_average = (
        float((current["home_goals"] + current["away_goals"]).mean())
        if not current.empty
        else float("nan")
    )
    historical_average = (
        float((historical["home_goals"] + historical["away_goals"]).mean())
        if not historical.empty
        else float("nan")
    )
    ratio = (
        current_average / historical_average
        if historical_average > 0 and not math.isnan(current_average)
        else float("nan")
    )
    if math.isnan(ratio):
        status = "insufficient_data"
    elif ratio >= 1.2:
        status = "higher_scoring"
    elif ratio <= 0.8:
        status = "lower_scoring"
    else:
        status = "normal_range"
    return {
        "current_year": current_year,
        "current_matches": int(len(current)),
        "current_goals_per_match": current_average,
        "historical_matches": int(len(historical)),
        "historical_goals_per_match": historical_average,
        "current_to_historical_ratio": ratio,
        "status": status,
    }
