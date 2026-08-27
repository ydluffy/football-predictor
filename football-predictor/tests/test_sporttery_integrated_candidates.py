from __future__ import annotations

import pandas as pd

from scripts.build_sporttery_integrated_candidates import build_integrated_candidates


def test_integrated_candidates_downgrade_calibrated_handicap_conflict():
    predictions = pd.DataFrame(
        [
            {
                "date": "2026-07-04",
                "match_id": "1",
                "stage": "LAST_16",
                "home_team": "Paraguay",
                "away_team": "France",
                "is_knockout": 1,
                "adjusted_p_home": 0.03,
                "adjusted_p_draw": 0.06,
                "adjusted_p_away": 0.91,
                "handicap_recommended_result": "让负",
                "handicap_home_win_probability": 0.21,
                "handicap_draw_probability": 0.17,
                "handicap_away_win_probability": 0.61,
                "handicap_label": "主队受让2球",
                "knockout_calibrated_handicap_result": "让胜",
                "knockout_calibration_risk_flags": "favorite_blowout_tail|deep_spread_conservative_override",
            }
        ]
    )

    out = build_integrated_candidates(predictions)
    handicap = out[out["play_type"].eq("handicap_spf")].iloc[0]

    assert handicap["selection"] == "让负"
    assert handicap["calibrated_selection"] == "让胜"
    assert handicap["calibrated_conflict"] == 1
    assert handicap["final_tier"] == "single_candidate"


def test_integrated_candidates_include_total_goals_and_low_probability_score():
    predictions = pd.DataFrame(
        [
            {
                "date": "2026-07-04",
                "match_id": "2",
                "stage": "LAST_16",
                "home_team": "Canada",
                "away_team": "Morocco",
                "is_knockout": 1,
                "adjusted_p_home": 0.14,
                "adjusted_p_draw": 0.35,
                "adjusted_p_away": 0.51,
                "sporttery_total_goals_1_probability": 0.34,
                "sporttery_total_goals_1_odds": 4.55,
                "sporttery_total_goals_1_market_probability": 0.18,
                "sporttery_total_goals_1_edge": 0.16,
                "sporttery_total_goals_1_expected_value": 0.56,
                "sporttery_total_goals_double_pick": "1/2",
                "knockout_calibrated_total_goals_pick": "小2.5",
                "sporttery_correct_score_best_selection": "0:0",
                "sporttery_correct_score_best_expected_value": 1.2,
                "sporttery_correct_score_best_edge": 0.16,
                "top_score_1": "0:1",
                "top_score_1_probability": 0.24,
                "top_score_2": "0:0",
                "top_score_2_probability": 0.23,
                "knockout_calibration_risk_flags": "high_90m_draw_risk|penalty_tail_risk|low_total_draw_cluster",
            }
        ]
    )

    out = build_integrated_candidates(predictions)
    total = out[(out["play_type"].eq("total_goals")) & out["selection"].eq("1")].iloc[0]
    score = out[out["play_type"].eq("correct_score")].iloc[0]

    assert total["final_tier"] in {"single_candidate", "small_stake_candidate"}
    assert score["selection"] == "0:0"
    assert score["final_tier"] != "main_candidate"
