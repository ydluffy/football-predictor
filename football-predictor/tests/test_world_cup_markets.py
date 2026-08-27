from __future__ import annotations

import numpy as np

from world_cup.markets import (
    correct_score_distribution,
    handicap_three_way,
    implied_probabilities_from_decimal_odds,
    infer_home_handicap,
    market_edge_analysis,
    summarize_score_markets,
    top_scorelines,
    total_goals_distribution,
)


def test_top_scorelines_returns_two_highest_scores():
    matrix = np.array([[0.1, 0.2], [0.4, 0.3]])

    out = top_scorelines(matrix, count=2)

    assert [row["score"] for row in out] == ["1:0", "1:1"]
    assert [row["probability"] for row in out] == [0.4, 0.3]


def test_handicap_minus_one_three_way():
    matrix = np.zeros((4, 4))
    matrix[2, 0] = 0.4
    matrix[1, 0] = 0.3
    matrix[0, 0] = 0.2
    matrix[0, 1] = 0.1

    out = handicap_three_way(matrix, home_handicap=-1.0)

    assert out["handicap_home_win"] == 0.4
    assert out["handicap_draw"] == 0.3
    assert abs(out["handicap_away_win"] - 0.3) < 1e-12
    assert out["handicap_label"] == "主队让1球"
    assert out["recommended_key"] == "handicap_home_win"
    assert out["recommended_result"] == "让胜"


def test_infer_home_handicap_from_expected_goal_gap():
    assert infer_home_handicap(2.5, 0.5) == -2.0
    assert infer_home_handicap(1.6, 0.9) == -1.0
    assert infer_home_handicap(1.1, 1.0) == 0.0
    assert infer_home_handicap(0.8, 1.6) == 1.0
    assert infer_home_handicap(0.5, 2.5) == 2.0


def test_total_goals_distribution_and_market_summary():
    matrix = np.zeros((4, 4))
    matrix[1, 0] = 0.2
    matrix[1, 1] = 0.3
    matrix[2, 1] = 0.4
    matrix[3, 1] = 0.1

    totals = total_goals_distribution(matrix)
    summary = summarize_score_markets(
        matrix,
        expected_home_goals=2.0,
        expected_away_goals=0.8,
    )

    assert totals["most_likely_total_goals"] == 3
    assert totals["over_2_5_probability"] == 0.5
    assert totals["sporttery_total_goal_probabilities"]["total_goals_1_probability"] == 0.2
    assert totals["sporttery_total_goal_probabilities"]["total_goals_3_probability"] == 0.4
    assert totals["top_total_goal_selections"][0]["selection"] == "3"
    assert len(summary["top_scorelines"]) == 2
    assert summary["correct_score"]["2:1"] == 0.4
    assert "recommended_result" in summary["handicap"]
    assert summary["handicap"]["home_handicap"] == -1.0


def test_correct_score_distribution_buckets_other_scores():
    matrix = np.zeros((7, 7))
    matrix[1, 0] = 0.2
    matrix[6, 0] = 0.3
    matrix[4, 4] = 0.1
    matrix[0, 6] = 0.4

    out = correct_score_distribution(matrix)

    assert out["1:0"] == 0.2
    assert out["home_other"] == 0.3
    assert out["draw_other"] == 0.1
    assert out["away_other"] == 0.4


def test_implied_probabilities_remove_overround():
    out = implied_probabilities_from_decimal_odds(
        {
            "home_win": 2.0,
            "draw": 4.0,
            "away_win": 4.0,
        }
    )

    assert abs(sum(value for value in out.values() if value is not None) - 1.0) < 1e-12
    assert out["home_win"] == 0.5
    assert out["draw"] == 0.25
    assert out["away_win"] == 0.25


def test_market_edge_analysis_flags_positive_model_edge():
    out = market_edge_analysis(
        {
            "home_win": 0.62,
            "draw": 0.20,
            "away_win": 0.18,
        },
        {
            "home_win": 2.0,
            "draw": 3.5,
            "away_win": 4.0,
        },
        min_edge=0.03,
    )

    assert out["best_key"] == "home_win"
    assert out["best_label"] == "主胜"
    assert out["best_edge"] > 0.1
    assert out["best_expected_value"] == 0.24
    assert out["signal"] == "positive"
