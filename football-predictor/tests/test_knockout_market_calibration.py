from world_cup.knockout_market_calibration import knockout_market_calibration


def test_knockout_calibration_dampens_high_draw_spread_call():
    out = knockout_market_calibration(
        is_knockout=True,
        p_home=0.142,
        p_draw=0.348,
        p_away=0.510,
        expected_home_goals=0.40,
        expected_away_goals=1.03,
        handicap_line=1.0,
        handicap_home_win_probability=0.49,
        handicap_draw_probability=0.30,
        handicap_away_win_probability=0.21,
        under_2_5_probability=0.826,
        over_2_5_probability=0.174,
        knockout_extra_time_probability=0.348,
        knockout_penalty_shootout_probability=0.243,
    )

    assert out["knockout_calibration_applied"] == 1
    assert out["knockout_calibrated_handicap_result"] == "让胜"
    assert out["knockout_calibrated_total_goals_pick"] == "小2.5"
    assert "low_total_draw_cluster" in out["knockout_calibration_risk_flags"]


def test_knockout_calibration_overrides_deep_spread_in_knockout():
    out = knockout_market_calibration(
        is_knockout=True,
        p_home=0.030,
        p_draw=0.063,
        p_away=0.907,
        expected_home_goals=0.74,
        expected_away_goals=3.99,
        handicap_line=2.0,
        handicap_home_win_probability=0.216,
        handicap_draw_probability=0.174,
        handicap_away_win_probability=0.610,
        under_2_5_probability=0.152,
        over_2_5_probability=0.848,
        knockout_extra_time_probability=0.063,
        knockout_penalty_shootout_probability=0.021,
    )

    assert out["knockout_calibration_applied"] == 1
    assert out["knockout_calibrated_handicap_result"] == "让胜"
    assert out["knockout_calibrated_total_goals_pick"] == "大2.5"
    assert "deep_spread_conservative_override" in out["knockout_calibration_risk_flags"]
    assert "favorite_blowout_tail" in out["knockout_calibration_risk_flags"]


def test_knockout_calibration_returns_empty_for_group_stage():
    out = knockout_market_calibration(
        is_knockout=False,
        p_home=0.4,
        p_draw=0.3,
        p_away=0.3,
        expected_home_goals=1.2,
        expected_away_goals=1.0,
        handicap_line=0,
        handicap_home_win_probability=0.4,
        handicap_draw_probability=0.3,
        handicap_away_win_probability=0.3,
        under_2_5_probability=0.55,
        over_2_5_probability=0.45,
    )

    assert out["knockout_calibration_applied"] == 0
    assert out["knockout_calibrated_handicap_result"] == ""
