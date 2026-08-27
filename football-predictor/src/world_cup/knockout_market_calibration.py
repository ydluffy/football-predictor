from __future__ import annotations


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def knockout_market_calibration(
    *,
    is_knockout: bool,
    p_home: float,
    p_draw: float,
    p_away: float,
    expected_home_goals: float,
    expected_away_goals: float,
    handicap_line: float,
    handicap_home_win_probability: float,
    handicap_draw_probability: float,
    handicap_away_win_probability: float,
    under_2_5_probability: float,
    over_2_5_probability: float,
    knockout_extra_time_probability: object = None,
    knockout_penalty_shootout_probability: object = None,
) -> dict[str, object]:
    """Add conservative knockout calibration signals for handicap and totals.

    This layer does not replace the base probabilities. It flags situations where
    knockout match dynamics make spread/total recommendations less reliable than
    the 1X2 direction.
    """

    if not is_knockout:
        return {
            "knockout_calibration_applied": 0,
            "knockout_calibrated_handicap_result": "",
            "knockout_calibrated_handicap_confidence": "",
            "knockout_calibrated_total_goals_pick": "",
            "knockout_calibrated_total_goals_confidence": "",
            "knockout_calibration_risk_flags": "",
        }

    p_home = _float(p_home)
    p_draw = _float(p_draw)
    p_away = _float(p_away)
    expected_home_goals = _float(expected_home_goals)
    expected_away_goals = _float(expected_away_goals)
    handicap_line = _float(handicap_line)
    handicap_probs = {
        "让胜": _float(handicap_home_win_probability),
        "让平": _float(handicap_draw_probability),
        "让负": _float(handicap_away_win_probability),
    }
    under_2_5_probability = _float(under_2_5_probability)
    over_2_5_probability = _float(over_2_5_probability)
    extra_time_probability = _float(knockout_extra_time_probability)
    penalty_probability = _float(knockout_penalty_shootout_probability)

    favorite_side = "home" if p_home >= p_away else "away"
    favorite_probability = max(p_home, p_away)
    favorite_goal_edge = abs(expected_home_goals - expected_away_goals)
    total_expected_goals = expected_home_goals + expected_away_goals
    handicap_depth = abs(handicap_line)
    risk_flags: list[str] = []

    if p_draw >= 0.28 or extra_time_probability >= 0.28:
        risk_flags.append("high_90m_draw_risk")
    if penalty_probability >= 0.14:
        risk_flags.append("penalty_tail_risk")
    if handicap_depth >= 2 and favorite_probability < 0.72:
        risk_flags.append("deep_handicap_without_strong_90m_edge")
    if handicap_depth >= 2 and total_expected_goals < 3.0:
        risk_flags.append("deep_handicap_low_goal_environment")
    if over_2_5_probability >= 0.75 and favorite_probability >= 0.80:
        risk_flags.append("favorite_blowout_tail")
    if under_2_5_probability >= 0.72 and p_draw >= 0.25:
        risk_flags.append("low_total_draw_cluster")

    calibrated_handicap = max(handicap_probs, key=handicap_probs.get)
    handicap_confidence = handicap_probs[calibrated_handicap]

    # Conservative overrides learned from knockout misses:
    # 1) Deep favorite spreads are fragile in low-goal knockout games.
    # 2) High draw risk should dampen any strong spread call.
    if handicap_depth >= 2:
        if favorite_side == "away" and handicap_line > 0:
            calibrated_handicap = "让胜"
        elif favorite_side == "home" and handicap_line < 0:
            calibrated_handicap = "让负"
        handicap_confidence = min(handicap_confidence, 0.48)
        risk_flags.append("deep_spread_conservative_override")
    elif p_draw >= 0.30 and handicap_depth >= 1:
        if favorite_side == "away" and handicap_line > 0:
            calibrated_handicap = "让胜"
        elif favorite_side == "home" and handicap_line < 0:
            calibrated_handicap = "让负"
        handicap_confidence = min(handicap_confidence, 0.52)
        risk_flags.append("draw_risk_spread_dampener")

    if over_2_5_probability > under_2_5_probability:
        total_pick = "大2.5"
        total_confidence = over_2_5_probability
    else:
        total_pick = "小2.5"
        total_confidence = under_2_5_probability

    if total_pick == "大2.5" and (
        p_draw >= 0.18
        or total_expected_goals < 3.3
        or (favorite_probability >= 0.80 and favorite_goal_edge < 1.8)
    ):
        total_confidence = min(total_confidence, 0.58)
        risk_flags.append("over_total_knockout_dampener")
    if total_pick == "小2.5" and favorite_goal_edge >= 0.9 and p_draw < 0.40:
        total_confidence = min(total_confidence, 0.62)
        risk_flags.append("under_total_favorite_can_break_game")

    return {
        "knockout_calibration_applied": 1,
        "knockout_calibrated_handicap_result": calibrated_handicap,
        "knockout_calibrated_handicap_confidence": handicap_confidence,
        "knockout_calibrated_total_goals_pick": total_pick,
        "knockout_calibrated_total_goals_confidence": total_confidence,
        "knockout_calibration_risk_flags": "|".join(dict.fromkeys(risk_flags)),
    }
