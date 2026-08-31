from __future__ import annotations

import pandas as pd
import pytest

from world_cup.market_research import (
    actual_1x2_result,
    actual_handicap_result,
    build_market_research_dataset,
    summarize_market_research,
    total_goals_bucket,
)


def test_actual_settlement_helpers():
    assert actual_1x2_result(0, 3) == "away"
    assert actual_1x2_result(1, 1) == "draw"
    assert actual_handicap_result(0, 3, 1) == "handicap_away"
    assert actual_handicap_result(0, 1, 2) == "handicap_home"
    assert actual_handicap_result(0, 2, 2) == "handicap_draw"
    assert total_goals_bucket(3, 4) == "7_plus"


def test_market_research_dataset_and_summary():
    predictions = pd.DataFrame(
        [
            {
                "date": "2026-07-04",
                "match_id": "537376",
                "stage": "LAST_16",
                "home_team": "Canada",
                "away_team": "Morocco",
                "adjusted_p_home": 0.14,
                "adjusted_p_draw": 0.35,
                "adjusted_p_away": 0.51,
                "spf_market_home_probability": 0.15,
                "spf_market_draw_probability": 0.24,
                "spf_market_away_probability": 0.61,
                "the_odds_api_market_home_probability": 0.17,
                "the_odds_api_market_draw_probability": 0.28,
                "the_odds_api_market_away_probability": 0.55,
                "handicap_line": 1,
                "handicap_label": "主队受让1球",
                "handicap_recommended_key": "handicap_home_win",
                "handicap_market_home_probability": 0.39,
                "handicap_market_draw_probability": 0.32,
                "handicap_market_away_probability": 0.29,
                "sporttery_total_goals_best_selection": "0",
                "knockout_calibration_risk_flags": "low_total_draw_cluster",
            },
            {
                "date": "2026-07-04",
                "match_id": "537377",
                "stage": "LAST_16",
                "home_team": "Paraguay",
                "away_team": "France",
                "adjusted_p_home": 0.03,
                "adjusted_p_draw": 0.06,
                "adjusted_p_away": 0.91,
                "the_odds_api_market_home_probability": 0.06,
                "the_odds_api_market_draw_probability": 0.14,
                "the_odds_api_market_away_probability": 0.80,
                "handicap_line": 2,
                "handicap_label": "主队受让2球",
                "handicap_recommended_key": "handicap_away_win",
                "handicap_market_home_probability": 0.39,
                "handicap_market_draw_probability": 0.28,
                "handicap_market_away_probability": 0.33,
                "sporttery_total_goals_best_selection": "4",
            },
        ]
    )
    results = pd.DataFrame(
        [
            {
                "match_id": "537376",
                "status": "FINISHED",
                "home_score": 0,
                "away_score": 3,
                "winner": "AWAY_TEAM",
            },
            {
                "match_id": "537377",
                "status": "FINISHED",
                "home_score": 0,
                "away_score": 1,
                "winner": "AWAY_TEAM",
            },
        ]
    )

    dataset = build_market_research_dataset(predictions, results)
    canada = dataset[dataset["home_team"].eq("Canada")].iloc[0]
    paraguay = dataset[dataset["home_team"].eq("Paraguay")].iloc[0]
    summary = summarize_market_research(dataset)

    assert canada["actual_1x2"] == "away"
    assert canada["model_1x2_hit"] == 1
    assert canada["sporttery_1x2_hit"] == 1
    assert canada["model_handicap_hit"] == 0
    assert canada["inner_outer_favorite_probability_gap"] == pytest.approx(0.06)
    assert paraguay["actual_handicap"] == "handicap_home"
    assert paraguay["sporttery_handicap_hit"] == 1
    assert paraguay["market_alignment"] == "model_outer_aligned"
    assert summary.finished_rows == 2
    assert summary.model_1x2_accuracy == 1.0
    assert summary.model_handicap_accuracy == 0.0
