import numpy as np

from world_cup.knockout import is_knockout_stage
from world_cup.knockout import knockout_adjustment


def _matrix(home_lambda: float, away_lambda: float) -> np.ndarray:
    home = np.array([0.2, 0.35, 0.3, 0.15])
    away = np.array([0.45, 0.32, 0.16, 0.07])
    if away_lambda > home_lambda:
        home, away = away, home
    out = np.outer(home, away)
    return out / out.sum()


def test_is_knockout_stage_recognizes_world_cup_rounds():
    assert is_knockout_stage("LAST_32")
    assert is_knockout_stage("quarter_finals")
    assert not is_knockout_stage("GROUP_STAGE")


def test_knockout_adjustment_clear_favorite_advances():
    result = knockout_adjustment(
        score_matrix=_matrix(2.0, 0.8),
        p_home=0.7,
        p_draw=0.18,
        p_away=0.12,
        expected_home_goals=2.0,
        expected_away_goals=0.8,
    )

    assert result["knockout_recommended_advancer"] == "home"
    assert result["knockout_home_advance_probability"] > 0.75
    assert result["knockout_risk_signal"] == "clear_favorite"


def test_knockout_adjustment_balanced_tie_has_penalty_risk():
    result = knockout_adjustment(
        score_matrix=_matrix(1.0, 1.0),
        p_home=0.32,
        p_draw=0.36,
        p_away=0.32,
        expected_home_goals=1.0,
        expected_away_goals=1.0,
    )

    assert result["knockout_penalty_shootout_probability"] > 0.15
    assert result["knockout_risk_signal"] == "high_draw_penalty_risk"
    assert abs(
        result["knockout_home_advance_probability"]
        - result["knockout_away_advance_probability"]
    ) < 0.02


def test_knockout_adjustment_flags_market_direction_conflict():
    result = knockout_adjustment(
        score_matrix=_matrix(0.8, 1.6),
        p_home=0.2,
        p_draw=0.25,
        p_away=0.55,
        expected_home_goals=0.8,
        expected_away_goals=1.6,
        market_home_probability=0.58,
        market_draw_probability=0.24,
        market_away_probability=0.18,
    )

    assert result["knockout_model_best_1x2"] == "away"
    assert result["knockout_market_best_1x2"] == "home"
    assert result["knockout_market_divergence_signal"] == "direction_conflict"
