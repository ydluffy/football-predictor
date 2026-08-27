from __future__ import annotations

import numpy as np
import pandas as pd

from evaluate.handicap_margin_movement_v3 import (
    build_movement_model_frame,
    margin_category_probabilities,
    run_handicap_margin_movement_v3,
)


def _matches() -> pd.DataFrame:
    rows = []
    margins = [-3, -2, -1, 0, 1, 2, 3]
    seasons = ("2019-20", "2020-21", "2021-22", "2022-23", "2023-24")
    for season_index, season in enumerate(seasons):
        for index in range(42):
            margin = margins[index % len(margins)]
            opening_line = -0.25 if margin > 0 else 0.25 if margin < 0 else 0.0
            closing_line = float(np.clip(-0.5 * margin, -1.5, 1.5))
            home_close = float(np.clip(0.50 + 0.06 * margin, 0.20, 0.80))
            rows.append(
                {
                    "match_id": f"v3-{season}-{index}",
                    "date": f"{2019 + season_index}-09-{index % 28 + 1:02d}",
                    "season": season,
                    "league": "E0",
                    "home_team": f"H{index % 10}",
                    "away_team": f"A{index % 10}",
                    "home_goals": max(margin, 0) + 1,
                    "away_goals": max(-margin, 0) + 1,
                    "AvgH": 2.2,
                    "AvgD": 3.2,
                    "AvgA": 3.1,
                    "AHh": opening_line,
                    "AvgAHH": 1.9,
                    "AvgAHA": 1.95,
                    "Avg>2.5": 1.9,
                    "Avg<2.5": 1.95,
                    "AvgCH": 1.0 / home_close + 0.15,
                    "AvgCD": 3.2,
                    "AvgCA": 1.0 / (1.0 - home_close) + 0.15,
                    "AHCh": closing_line,
                    "AvgCAHH": 1.0 / home_close + 0.10,
                    "AvgCAHA": 1.0 / (1.0 - home_close) + 0.10,
                    "AvgC>2.5": 1.85 if abs(margin) >= 2 else 2.05,
                    "AvgC<2.5": 2.05 if abs(margin) >= 2 else 1.85,
                }
            )
    return pd.DataFrame(rows)


def test_margin_categories_split_exactly_one_from_two_plus():
    probabilities = np.zeros((1, 9))
    probabilities[0, MARGIN_INDEX_ZERO := 4] = 0.2
    probabilities[0, MARGIN_INDEX_ZERO + 1] = 0.3
    probabilities[0, MARGIN_INDEX_ZERO + 2] = 0.5

    categories = margin_category_probabilities(probabilities)

    assert categories["home_not_win"][0] == 0.2
    assert categories["home_win_exactly_1"][0] == 0.3
    assert categories["home_win_2_plus"][0] == 0.5
    assert categories["home_win"][0] == 0.8


def test_movement_frame_uses_pregame_open_close_changes():
    frame, audit = build_movement_model_frame(_matches())

    assert len(frame) == len(_matches())
    assert "home_line_strength_delta" in frame
    assert "favorite_hot_without_line_support" in frame
    assert audit["uses_pregame_closing_proxy"] is True
    assert audit["uses_post_kickoff_data"] is False


def test_v3_runs_expanding_holdouts_and_remains_shadow_only():
    predictions, folds, payload = run_handicap_margin_movement_v3(
        _matches(),
        min_train_seasons=2,
        n_bootstrap=100,
        time_aligned_events=7,
        settled_shadow_plans=0,
    )

    assert set(folds["holdout_season"]) == {"2021-22", "2022-23", "2023-24"}
    assert predictions["v3_probability_h"].between(0.0, 1.0).all()
    assert predictions["margin_probability_home_win_exactly_1"].between(0.0, 1.0).all()
    assert payload["report"]["mode"] == "shadow_only"
    assert payload["report"]["production_promotion_allowed"] is False
    assert payload["report"]["production_change_performed"] is False
