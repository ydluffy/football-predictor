from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from evaluate.metrics import compute_metrics
from world_cup.model import WorldCupBaselineModel


@dataclass
class TournamentGoalEnvironment:
    prior_matches: float = 16.0
    responsiveness: float = 1.0
    min_observed_matches: int = 0
    min_scale: float = 0.8
    max_scale: float = 1.25
    observed_matches: int = 0
    actual_goals: float = 0.0
    expected_goals: float = 0.0

    def scale(self) -> float:
        if (
            self.observed_matches < self.min_observed_matches
            or self.observed_matches == 0
            or self.expected_goals <= 0
        ):
            return 1.0
        raw_ratio = self.actual_goals / self.expected_goals
        evidence_weight = self.observed_matches / (
            self.observed_matches + self.prior_matches
        )
        adjusted = 1.0 + self.responsiveness * evidence_weight * (raw_ratio - 1.0)
        return float(np.clip(adjusted, self.min_scale, self.max_scale))

    def update_batch(
        self,
        *,
        actual_goals: float,
        expected_goals: float,
        matches: int,
    ) -> None:
        self.actual_goals += float(actual_goals)
        self.expected_goals += float(expected_goals)
        self.observed_matches += int(matches)


def _poisson_nll(actual: int, expected: float) -> float:
    expected = max(float(expected), 1e-12)
    return expected - actual * math.log(expected) + math.lgamma(actual + 1)


def evaluate_dynamic_goal_environment(
    matches: pd.DataFrame,
    *,
    holdout_years: tuple[int, ...] = (2010, 2014, 2018, 2022),
    prior_matches: float = 16.0,
    responsiveness: float = 1.0,
    min_observed_matches: int = 0,
) -> pd.DataFrame:
    data = matches[matches["date"] >= pd.Timestamp("2000-01-01")].copy()
    rows = []
    for holdout_year in holdout_years:
        tournament = data[
            data["tournament"].astype(str).eq("FIFA World Cup")
            & data["date"].dt.year.eq(int(holdout_year))
        ].sort_values("date", kind="mergesort")
        if tournament.empty:
            continue
        start = tournament["date"].min()
        model = WorldCupBaselineModel().fit(data[data["date"] < start])
        environment = TournamentGoalEnvironment(
            prior_matches=prior_matches,
            responsiveness=responsiveness,
            min_observed_matches=min_observed_matches,
        )
        prediction_rows = []

        for _, day in tournament.groupby("date", sort=True):
            scale = environment.scale()
            day_expected = 0.0
            day_actual = 0.0
            for match in day.itertuples(index=False):
                prediction = model.predict_match(
                    match.home_team,
                    match.away_team,
                    neutral=bool(match.neutral),
                    goal_scale=scale,
                )
                expected_total = (
                    float(prediction["expected_home_goals"])
                    + float(prediction["expected_away_goals"])
                )
                actual_total = int(match.home_goals) + int(match.away_goals)
                prediction_rows.append(
                    {
                        "actual_result": str(match.actual_result),
                        "p_home": float(prediction["p_home"]),
                        "p_draw": float(prediction["p_draw"]),
                        "p_away": float(prediction["p_away"]),
                        "expected_total_goals": expected_total,
                        "actual_total_goals": actual_total,
                        "goal_scale": scale,
                        "total_goal_nll": _poisson_nll(actual_total, expected_total),
                        "over_2_5_probability": float(
                            1.0
                            - math.exp(-expected_total)
                            * (
                                1.0
                                + expected_total
                                + expected_total**2 / 2.0
                            )
                        ),
                    }
                )
                day_expected += expected_total
                day_actual += actual_total
            environment.update_batch(
                actual_goals=day_actual,
                expected_goals=day_expected,
                matches=len(day),
            )

        predictions = pd.DataFrame(prediction_rows)
        metrics = compute_metrics(
            predictions["actual_result"],
            predictions[["p_home", "p_draw", "p_away"]],
        )
        over_actual = (predictions["actual_total_goals"] >= 3).astype(float)
        rows.append(
            {
                "holdout_year": int(holdout_year),
                "prior_matches": float(prior_matches),
                "responsiveness": float(responsiveness),
                "min_observed_matches": int(min_observed_matches),
                "matches": int(len(predictions)),
                "logloss": float(metrics["logloss"]),
                "brier": float(metrics["brier"]),
                "goal_mae": float(
                    np.mean(
                        np.abs(
                            predictions["actual_total_goals"]
                            - predictions["expected_total_goals"]
                        )
                    )
                ),
                "total_goal_nll": float(predictions["total_goal_nll"].mean()),
                "over_2_5_brier": float(
                    np.mean(
                        (predictions["over_2_5_probability"] - over_actual) ** 2
                    )
                ),
                "mean_goal_scale": float(predictions["goal_scale"].mean()),
                "final_goal_scale": float(environment.scale()),
                "actual_goals_per_match": float(
                    predictions["actual_total_goals"].mean()
                ),
                "expected_goals_per_match": float(
                    predictions["expected_total_goals"].mean()
                ),
            }
        )
    return pd.DataFrame(rows)


def compare_dynamic_goal_parameters(
    matches: pd.DataFrame,
    *,
    prior_options: tuple[float, ...] = (16.0,),
    responsiveness_options: tuple[float, ...] = (0.0, 0.5, 1.0),
    minimum_observation_options: tuple[int, ...] = (4, 8, 12),
) -> pd.DataFrame:
    frames = []
    for prior_matches in prior_options:
        for responsiveness in responsiveness_options:
            observation_options = (
                (0,) if responsiveness == 0.0 else minimum_observation_options
            )
            for min_observed_matches in observation_options:
                frames.append(
                    evaluate_dynamic_goal_environment(
                        matches,
                        prior_matches=prior_matches,
                        responsiveness=responsiveness,
                        min_observed_matches=min_observed_matches,
                    )
                )
    return pd.concat(frames, ignore_index=True)


def estimate_live_goal_environment(
    model: WorldCupBaselineModel,
    completed_tournament: pd.DataFrame,
    *,
    prior_matches: float = 16.0,
    responsiveness: float = 1.0,
    min_observed_matches: int = 4,
) -> TournamentGoalEnvironment:
    environment = TournamentGoalEnvironment(
        prior_matches=prior_matches,
        responsiveness=responsiveness,
        min_observed_matches=min_observed_matches,
    )
    data = completed_tournament.sort_values("date", kind="mergesort")
    for _, day in data.groupby("date", sort=True):
        scale = environment.scale()
        expected = 0.0
        actual = 0.0
        for match in day.itertuples(index=False):
            prediction = model.predict_match(
                match.home_team,
                match.away_team,
                neutral=bool(getattr(match, "neutral", True)),
                goal_scale=scale,
            )
            expected += float(prediction["expected_home_goals"]) + float(
                prediction["expected_away_goals"]
            )
            actual += int(match.home_goals) + int(match.away_goals)
        environment.update_batch(
            actual_goals=actual,
            expected_goals=expected,
            matches=len(day),
        )
    return environment


def over_2_5_probability(expected_total_goals: float) -> float:
    expected = max(float(expected_total_goals), 0.0)
    return float(
        1.0
        - math.exp(-expected)
        * (1.0 + expected + expected**2 / 2.0)
    )
