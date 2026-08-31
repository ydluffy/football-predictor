from __future__ import annotations

import math
from typing import Mapping

import numpy as np


KNOCKOUT_STAGES = {
    "LAST_32",
    "LAST_16",
    "QUARTER_FINALS",
    "SEMI_FINALS",
    "THIRD_PLACE",
    "FINAL",
}


def is_knockout_stage(stage: object) -> bool:
    return str(stage or "").strip().upper() in KNOCKOUT_STAGES


def _poisson_probabilities(lam: float, max_goals: int) -> np.ndarray:
    lam = max(float(lam), 1e-9)
    values = np.array(
        [math.exp(-lam) * lam**goals / math.factorial(goals) for goals in range(max_goals + 1)],
        dtype=float,
    )
    total = float(values.sum())
    if total <= 1e-12:
        values[0] = 1.0
        return values
    return values / total


def _score_matrix_from_lambdas(
    home_goals: float,
    away_goals: float,
    *,
    max_goals: int = 6,
) -> np.ndarray:
    home = _poisson_probabilities(home_goals, max_goals)
    away = _poisson_probabilities(away_goals, max_goals)
    matrix = np.outer(home, away)
    return matrix / matrix.sum()


def _three_way_from_matrix(score_matrix: np.ndarray) -> dict[str, float]:
    home = 0.0
    draw = 0.0
    away = 0.0
    matrix = np.asarray(score_matrix, dtype=float)
    for home_goals in range(matrix.shape[0]):
        for away_goals in range(matrix.shape[1]):
            probability = float(matrix[home_goals, away_goals])
            if home_goals > away_goals:
                home += probability
            elif home_goals < away_goals:
                away += probability
            else:
                draw += probability
    return {"home": home, "draw": draw, "away": away}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _best_key(probabilities: Mapping[str, object]) -> str:
    numeric: dict[str, float] = {}
    for key, value in probabilities.items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            numeric[key] = number
    if not numeric:
        return ""
    return max(numeric, key=numeric.get)


def knockout_adjustment(
    *,
    score_matrix: np.ndarray,
    p_home: float,
    p_draw: float,
    p_away: float,
    expected_home_goals: float,
    expected_away_goals: float,
    market_home_probability: object = None,
    market_draw_probability: object = None,
    market_away_probability: object = None,
) -> dict[str, object]:
    """Estimate knockout-specific advancement and uncertainty from a 90-minute model.

    The base model still owns 90-minute probabilities. This layer adds a conservative
    extra-time and penalty estimate so knockout fixtures can be reviewed separately
    from ordinary group-stage 1X2 predictions.
    """

    p_home = float(p_home)
    p_draw = float(p_draw)
    p_away = float(p_away)
    total = max(p_home + p_draw + p_away, 1e-12)
    p_home, p_draw, p_away = p_home / total, p_draw / total, p_away / total

    # Extra time tends to be lower-event than a simple 30/90 split.
    extra_time_matrix = _score_matrix_from_lambdas(
        float(expected_home_goals) / 3.0 * 0.82,
        float(expected_away_goals) / 3.0 * 0.82,
        max_goals=max(4, min(6, np.asarray(score_matrix).shape[0] - 1)),
    )
    extra = _three_way_from_matrix(extra_time_matrix)
    penalty_home = _clamp(0.5 + (p_home - p_away) * 0.18, 0.38, 0.62)
    penalty_away = 1.0 - penalty_home

    home_advance = p_home + p_draw * (extra["home"] + extra["draw"] * penalty_home)
    away_advance = p_away + p_draw * (extra["away"] + extra["draw"] * penalty_away)
    advance_total = max(home_advance + away_advance, 1e-12)
    home_advance /= advance_total
    away_advance /= advance_total

    penalty_probability = p_draw * extra["draw"]
    upset_pressure = min(home_advance, away_advance)
    knockout_volatility = p_draw + penalty_probability + upset_pressure * 0.35
    if penalty_probability >= 0.16 or p_draw >= 0.32:
        knockout_risk = "high_draw_penalty_risk"
    elif upset_pressure >= 0.30:
        knockout_risk = "balanced_tie"
    elif max(home_advance, away_advance) >= 0.72:
        knockout_risk = "clear_favorite"
    else:
        knockout_risk = "moderate"

    market_probabilities = {
        "home": market_home_probability,
        "draw": market_draw_probability,
        "away": market_away_probability,
    }
    model_best = _best_key({"home": p_home, "draw": p_draw, "away": p_away})
    market_best = _best_key(market_probabilities)
    market_edges: dict[str, float | None] = {}
    for key, market_probability in market_probabilities.items():
        try:
            market_value = float(market_probability)
        except (TypeError, ValueError):
            market_edges[key] = None
            continue
        if not math.isfinite(market_value):
            market_edges[key] = None
            continue
        market_edges[key] = {"home": p_home, "draw": p_draw, "away": p_away}[key] - market_value
    valid_edges = {key: abs(value) for key, value in market_edges.items() if value is not None}
    max_market_gap = max(valid_edges.values()) if valid_edges else None
    if not valid_edges:
        divergence_signal = "no_market"
    elif model_best and market_best and model_best != market_best:
        divergence_signal = "direction_conflict"
    elif max_market_gap is not None and max_market_gap >= 0.15:
        divergence_signal = "large_probability_gap"
    elif max_market_gap is not None and max_market_gap >= 0.08:
        divergence_signal = "watch_gap"
    else:
        divergence_signal = "aligned"

    advance_key = "home" if home_advance >= away_advance else "away"
    return {
        "knockout_extra_time_probability": p_draw,
        "knockout_penalty_shootout_probability": penalty_probability,
        "knockout_home_extra_time_win_probability": extra["home"],
        "knockout_extra_time_draw_probability": extra["draw"],
        "knockout_away_extra_time_win_probability": extra["away"],
        "knockout_home_penalty_win_probability": penalty_home,
        "knockout_away_penalty_win_probability": penalty_away,
        "knockout_home_advance_probability": home_advance,
        "knockout_away_advance_probability": away_advance,
        "knockout_recommended_advancer": advance_key,
        "knockout_recommended_advancer_probability": max(home_advance, away_advance),
        "knockout_volatility_score": _clamp(knockout_volatility, 0.0, 1.0),
        "knockout_risk_signal": knockout_risk,
        "knockout_market_best_1x2": market_best,
        "knockout_model_best_1x2": model_best,
        "knockout_market_max_probability_gap": max_market_gap,
        "knockout_market_divergence_signal": divergence_signal,
        "knockout_market_home_edge": market_edges["home"],
        "knockout_market_draw_edge": market_edges["draw"],
        "knockout_market_away_edge": market_edges["away"],
    }


def empty_knockout_adjustment() -> dict[str, object]:
    return {
        "knockout_extra_time_probability": "",
        "knockout_penalty_shootout_probability": "",
        "knockout_home_extra_time_win_probability": "",
        "knockout_extra_time_draw_probability": "",
        "knockout_away_extra_time_win_probability": "",
        "knockout_home_penalty_win_probability": "",
        "knockout_away_penalty_win_probability": "",
        "knockout_home_advance_probability": "",
        "knockout_away_advance_probability": "",
        "knockout_recommended_advancer": "",
        "knockout_recommended_advancer_probability": "",
        "knockout_volatility_score": "",
        "knockout_risk_signal": "",
        "knockout_market_best_1x2": "",
        "knockout_model_best_1x2": "",
        "knockout_market_max_probability_gap": "",
        "knockout_market_divergence_signal": "",
        "knockout_market_home_edge": "",
        "knockout_market_draw_edge": "",
        "knockout_market_away_edge": "",
    }
