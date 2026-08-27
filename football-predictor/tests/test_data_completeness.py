from __future__ import annotations

from world_cup.data_completeness import data_completeness_summary


def test_data_completeness_scores_rich_prediction_higher():
    rich = data_completeness_summary(
        {
            "home_player_strength_confidence": 1.0,
            "away_player_strength_confidence": 1.0,
            "home_lineup_confirmed": 1,
            "away_lineup_confirmed": 1,
            "handicap_line_source": "sporttery",
            "spf_market_home_probability": 0.4,
            "spf_market_draw_probability": 0.3,
            "spf_market_away_probability": 0.3,
            "handicap_market_home_probability": 0.4,
            "handicap_market_draw_probability": 0.3,
            "handicap_market_away_probability": 0.3,
            "leisu_public_match_linked": 1,
            "leisu_has_intelligence": 1,
            "line_movement_snapshots": 2,
            "home_absence_count": 1,
            "home_absence_weighted_impact": 1.0,
        }
    )
    thin = data_completeness_summary({})

    assert rich["data_completeness_score"] == 1.0
    assert rich["data_completeness_grade"] == "A"
    assert thin["data_completeness_score"] == 0.1
    assert thin["data_completeness_grade"] == "D"
    assert "confirmed_lineups" in thin["data_completeness_missing"]


def test_data_completeness_handles_partial_market_data():
    out = data_completeness_summary(
        {
            "handicap_line_source": "sporttery",
            "handicap_market_home_probability": 0.4,
            "handicap_market_draw_probability": 0.3,
            "handicap_market_away_probability": 0.3,
        }
    )

    assert out["data_component_sporttery_handicap"] == 1.0
    assert out["data_component_handicap_market_odds"] == 1.0
    assert out["data_component_spf_market_odds"] == 0.0
    assert out["data_completeness_grade"] == "D"
