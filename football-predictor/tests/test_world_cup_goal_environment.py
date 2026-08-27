from __future__ import annotations

import pandas as pd

from world_cup.goal_environment import (
    TournamentGoalEnvironment,
    estimate_live_goal_environment,
    evaluate_dynamic_goal_environment,
    over_2_5_probability,
)
from world_cup.model import WorldCupBaselineModel


def test_goal_scale_increases_expected_goals_and_reduces_draw_probability():
    model = WorldCupBaselineModel()
    baseline = model.predict_match("A", "B", goal_scale=1.0)
    adjusted = model.predict_match("A", "B", goal_scale=1.2)

    assert adjusted["expected_home_goals"] > baseline["expected_home_goals"]
    assert adjusted["expected_away_goals"] > baseline["expected_away_goals"]
    assert adjusted["p_draw"] < baseline["p_draw"]
    assert adjusted["goal_environment_scale"] == 1.2


def test_goal_environment_uses_shrinkage_and_bounds():
    environment = TournamentGoalEnvironment(
        prior_matches=8,
        max_scale=1.25,
    )
    environment.update_batch(actual_goals=7, expected_goals=4, matches=2)

    assert environment.scale() == 1.15

    environment.update_batch(actual_goals=100, expected_goals=10, matches=20)
    assert environment.scale() == 1.25


def test_goal_environment_waits_for_minimum_completed_matches():
    environment = TournamentGoalEnvironment(
        prior_matches=8,
        min_observed_matches=4,
    )
    environment.update_batch(actual_goals=9, expected_goals=4, matches=3)
    assert environment.scale() == 1.0

    environment.update_batch(actual_goals=3, expected_goals=2, matches=1)
    assert environment.scale() > 1.0


def test_dynamic_evaluation_updates_only_after_date_batch():
    rows = [
        {
            "date": pd.Timestamp("2009-01-01"),
            "home_team": "A",
            "away_team": "B",
            "home_goals": 1,
            "away_goals": 0,
            "actual_result": "H",
            "tournament": "Friendly",
            "neutral": True,
            "importance": 0.55,
        },
        {
            "date": pd.Timestamp("2010-06-11"),
            "home_team": "A",
            "away_team": "B",
            "home_goals": 10,
            "away_goals": 10,
            "actual_result": "D",
            "tournament": "FIFA World Cup",
            "neutral": True,
            "importance": 1.5,
        },
        {
            "date": pd.Timestamp("2010-06-11"),
            "home_team": "B",
            "away_team": "A",
            "home_goals": 10,
            "away_goals": 10,
            "actual_result": "D",
            "tournament": "FIFA World Cup",
            "neutral": True,
            "importance": 1.5,
        },
        {
            "date": pd.Timestamp("2010-06-12"),
            "home_team": "A",
            "away_team": "B",
            "home_goals": 2,
            "away_goals": 2,
            "actual_result": "D",
            "tournament": "FIFA World Cup",
            "neutral": True,
            "importance": 1.5,
        },
    ]

    out = evaluate_dynamic_goal_environment(
        pd.DataFrame(rows),
        holdout_years=(2010,),
        prior_matches=1,
        responsiveness=1.0,
    )

    assert out.loc[0, "mean_goal_scale"] > 1.0
    assert out.loc[0, "final_goal_scale"] == 1.25
    assert out.loc[0, "matches"] == 3


def test_live_environment_and_over_probability():
    model = WorldCupBaselineModel()
    completed = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-06-10") + pd.Timedelta(days=index),
                "home_team": "A",
                "away_team": "B",
                "home_goals": 3,
                "away_goals": 2,
                "neutral": True,
            }
            for index in range(4)
        ]
    )

    environment = estimate_live_goal_environment(
        model,
        completed,
        prior_matches=4,
        min_observed_matches=4,
    )

    assert environment.observed_matches == 4
    assert environment.scale() > 1.0
    assert over_2_5_probability(3.0) > over_2_5_probability(2.0)
