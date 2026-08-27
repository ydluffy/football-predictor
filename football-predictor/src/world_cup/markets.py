from __future__ import annotations

import numpy as np


HANDICAP_RESULT_LABELS = {
    "handicap_home_win": "让胜",
    "handicap_draw": "让平",
    "handicap_away_win": "让负",
}


RESULT_LABELS = {
    "home_win": "主胜",
    "draw": "平",
    "away_win": "客胜",
    "handicap_home_win": "让胜",
    "handicap_draw": "让平",
    "handicap_away_win": "让负",
}


def infer_home_handicap(
    expected_home_goals: float,
    expected_away_goals: float,
) -> float:
    diff = float(expected_home_goals) - float(expected_away_goals)
    if diff >= 1.8:
        return -2.0
    if diff >= 0.5:
        return -1.0
    if diff <= -1.8:
        return 2.0
    if diff <= -0.5:
        return 1.0
    return 0.0


def handicap_label(home_handicap: float) -> str:
    line = float(home_handicap)
    if line < 0:
        return f"主队让{abs(line):g}球"
    if line > 0:
        return f"主队受让{line:g}球"
    return "平手盘"


def top_scorelines(score_matrix: np.ndarray, *, count: int = 2) -> list[dict[str, object]]:
    matrix = np.asarray(score_matrix, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("score matrix must be two-dimensional")
    if count < 1:
        raise ValueError("count must be at least 1")
    candidates = [
        (float(matrix[home_goals, away_goals]), home_goals, away_goals)
        for home_goals in range(matrix.shape[0])
        for away_goals in range(matrix.shape[1])
    ]
    candidates.sort(key=lambda item: (-item[0], item[1] + item[2], item[1]))
    return [
        {
            "home_goals": int(home_goals),
            "away_goals": int(away_goals),
            "score": f"{home_goals}:{away_goals}",
            "probability": probability,
        }
        for probability, home_goals, away_goals in candidates[:count]
    ]


def handicap_three_way(
    score_matrix: np.ndarray,
    *,
    home_handicap: float,
) -> dict[str, float | str]:
    matrix = np.asarray(score_matrix, dtype=float)
    home_win = 0.0
    draw = 0.0
    away_win = 0.0
    for home_goals in range(matrix.shape[0]):
        for away_goals in range(matrix.shape[1]):
            adjusted_margin = home_goals + home_handicap - away_goals
            probability = float(matrix[home_goals, away_goals])
            if adjusted_margin > 1e-12:
                home_win += probability
            elif adjusted_margin < -1e-12:
                away_win += probability
            else:
                draw += probability
    probabilities = {
        "handicap_home_win": home_win,
        "handicap_draw": draw,
        "handicap_away_win": away_win,
    }
    best = max(probabilities, key=probabilities.get)
    return {
        "home_handicap": float(home_handicap),
        "handicap_label": handicap_label(home_handicap),
        **probabilities,
        "recommended_key": best,
        "recommended_result": HANDICAP_RESULT_LABELS[best],
        "recommended_probability": probabilities[best],
    }


def total_goals_distribution(
    score_matrix: np.ndarray,
    *,
    max_exact_total: int = 6,
) -> dict[str, object]:
    matrix = np.asarray(score_matrix, dtype=float)
    maximum = matrix.shape[0] + matrix.shape[1] - 2
    exact = np.zeros(maximum + 1, dtype=float)
    for home_goals in range(matrix.shape[0]):
        for away_goals in range(matrix.shape[1]):
            exact[home_goals + away_goals] += matrix[home_goals, away_goals]
    displayed = {
        str(total): float(exact[total])
        for total in range(min(max_exact_total, maximum) + 1)
    }
    if maximum > max_exact_total:
        displayed[f"{max_exact_total + 1}球及以上"] = float(
            exact[max_exact_total + 1 :].sum()
        )
    most_likely_total = int(exact.argmax())
    sporttery_exact = {}
    for selection, probability in displayed.items():
        normalized_selection = (
            str(selection)
            .replace("çƒåŠä»¥ä¸Š", "+")
            .replace("球及以上", "+")
        )
        if normalized_selection.endswith("+"):
            key = f"total_goals_{normalized_selection[:-1]}_plus_probability"
        else:
            key = f"total_goals_{normalized_selection}_probability"
        sporttery_exact[key] = float(probability)
    ranked_totals = sorted(
        [
            {
                "selection": (
                    str(selection)
                    .replace("çƒåŠä»¥ä¸Š", "+")
                    .replace("球及以上", "+")
                    .replace("+", "_plus")
                ),
                "probability": float(probability),
            }
            for selection, probability in displayed.items()
        ],
        key=lambda item: (-float(item["probability"]), str(item["selection"])),
    )
    return {
        "most_likely_total_goals": most_likely_total,
        "most_likely_total_probability": float(exact[most_likely_total]),
        "exact_total_probabilities": displayed,
        "sporttery_total_goal_probabilities": sporttery_exact,
        "top_total_goal_selections": ranked_totals,
        "under_2_5_probability": float(exact[:3].sum()),
        "over_2_5_probability": float(exact[3:].sum()),
        "under_3_5_probability": float(exact[:4].sum()),
        "over_3_5_probability": float(exact[4:].sum()),
    }


def correct_score_distribution(
    score_matrix: np.ndarray,
) -> dict[str, float]:
    matrix = np.asarray(score_matrix, dtype=float)
    selections = {
        "1:0",
        "2:0",
        "2:1",
        "3:0",
        "3:1",
        "3:2",
        "4:0",
        "4:1",
        "4:2",
        "5:0",
        "5:1",
        "5:2",
        "0:0",
        "1:1",
        "2:2",
        "3:3",
        "0:1",
        "0:2",
        "1:2",
        "0:3",
        "1:3",
        "2:3",
        "0:4",
        "1:4",
        "2:4",
        "0:5",
        "1:5",
        "2:5",
    }
    probabilities = {selection: 0.0 for selection in selections}
    probabilities.update({"home_other": 0.0, "draw_other": 0.0, "away_other": 0.0})
    for home_goals in range(matrix.shape[0]):
        for away_goals in range(matrix.shape[1]):
            probability = float(matrix[home_goals, away_goals])
            score = f"{home_goals}:{away_goals}"
            if score in probabilities:
                probabilities[score] += probability
            elif home_goals > away_goals:
                probabilities["home_other"] += probability
            elif home_goals == away_goals:
                probabilities["draw_other"] += probability
            else:
                probabilities["away_other"] += probability
    return probabilities


def summarize_score_markets(
    score_matrix: np.ndarray,
    *,
    home_handicap: float | None = None,
    expected_home_goals: float | None = None,
    expected_away_goals: float | None = None,
) -> dict[str, object]:
    if home_handicap is None:
        if expected_home_goals is None or expected_away_goals is None:
            home_handicap = -1.0
        else:
            home_handicap = infer_home_handicap(expected_home_goals, expected_away_goals)
    return {
        "top_scorelines": top_scorelines(score_matrix, count=2),
        "handicap": handicap_three_way(
            score_matrix,
            home_handicap=float(home_handicap),
        ),
        "total_goals": total_goals_distribution(score_matrix),
        "correct_score": correct_score_distribution(score_matrix),
    }


def implied_probabilities_from_decimal_odds(
    odds: dict[str, object],
) -> dict[str, float | None]:
    raw: dict[str, float] = {}
    for key, value in odds.items():
        try:
            odd = float(value)
        except (TypeError, ValueError):
            continue
        if odd > 1e-12:
            raw[key] = 1.0 / odd
    overround = sum(raw.values())
    if not raw or overround <= 1e-12:
        return {key: None for key in odds}
    return {
        key: (raw[key] / overround if key in raw else None)
        for key in odds
    }


def market_edge_analysis(
    model_probabilities: dict[str, object],
    decimal_odds: dict[str, object],
    *,
    min_edge: float = 0.05,
) -> dict[str, object]:
    market_probabilities = implied_probabilities_from_decimal_odds(decimal_odds)
    edges: dict[str, float | None] = {}
    expected_values: dict[str, float | None] = {}
    for key, market_probability in market_probabilities.items():
        if market_probability is None:
            edges[key] = None
            expected_values[key] = None
            continue
        try:
            model_probability = float(model_probabilities[key])
            odd = float(decimal_odds[key])
        except (KeyError, TypeError, ValueError):
            edges[key] = None
            expected_values[key] = None
            continue
        edges[key] = model_probability - market_probability
        expected_values[key] = model_probability * odd - 1.0

    valid_edges = {key: value for key, value in edges.items() if value is not None}
    if not valid_edges:
        return {
            "market_probabilities": market_probabilities,
            "edges": edges,
            "expected_values": expected_values,
            "best_key": "",
            "best_label": "",
            "best_edge": None,
            "best_expected_value": None,
            "signal": "no_market",
        }
    best_key = max(valid_edges, key=lambda key: valid_edges[key])
    best_edge = valid_edges[best_key]
    best_ev = expected_values.get(best_key)
    signal = "positive" if best_edge >= min_edge else "watch"
    if best_ev is not None and best_ev < 0:
        signal = "probability_edge_only"
    return {
        "market_probabilities": market_probabilities,
        "edges": edges,
        "expected_values": expected_values,
        "best_key": best_key,
        "best_label": RESULT_LABELS.get(best_key, best_key),
        "best_edge": best_edge,
        "best_expected_value": best_ev,
        "signal": signal,
    }
