from __future__ import annotations

import numpy as np
import pandas as pd

from evaluate.sporttery_handicap_model import (
    MARGIN_CLASSES,
    actual_rqspf_result,
    build_handicap_model_frame,
    margin_to_rqspf_probabilities,
    run_sporttery_handicap_research,
)


def test_margin_distribution_converts_to_integer_handicap_probabilities():
    probabilities = np.zeros((1, len(MARGIN_CLASSES)))
    probabilities[0, MARGIN_CLASSES == 0] = 0.2
    probabilities[0, MARGIN_CLASSES == 1] = 0.5
    probabilities[0, MARGIN_CLASSES == 2] = 0.3
    rqspf = margin_to_rqspf_probabilities(probabilities, -1)
    assert np.allclose(rqspf, [[0.3, 0.5, 0.2]])
    assert actual_rqspf_result(2, -1) == "H"
    assert actual_rqspf_result(1, -1) == "D"
    assert actual_rqspf_result(0, -1) == "A"


def _matches() -> pd.DataFrame:
    rows = []
    margins = [-2, -1, 0, 1, 2, 3]
    for season_index, season in enumerate(("2020-21", "2021-22", "2022-23")):
        for index in range(60):
            margin = margins[index % len(margins)]
            home_goals = max(margin, 0) + 1
            away_goals = max(-margin, 0) + 1
            line = -0.25 * margin
            rows.append(
                {
                    "match_id": f"m-{season}-{index}", "date": f"{2020 + season_index}-09-{index % 28 + 1:02d}",
                    "season": season, "league": "E0", "home_team": f"H{index % 8}", "away_team": f"A{index % 8}",
                    "home_goals": home_goals, "away_goals": away_goals,
                    "AvgH": 2.2, "AvgD": 3.2, "AvgA": 3.1, "AHh": line,
                    "AvgAHH": 1.9, "AvgAHA": 1.95, "Avg>2.5": 1.9, "Avg<2.5": 1.95,
                }
            )
    return pd.DataFrame(rows)


def test_model_frame_uses_only_opening_market_fields():
    frame, audit = build_handicap_model_frame(_matches())
    assert len(frame) == 180
    assert audit["uses_closing_odds"] is False
    assert frame["season_progress"].between(0, 1).all()


def test_rolling_research_outputs_four_scenarios_per_holdout_match():
    predictions, folds, payload = run_sporttery_handicap_research(
        _matches(), min_train_seasons=2, n_bootstrap=100
    )
    assert predictions["match_id"].nunique() == 60
    assert len(predictions) == 240
    assert len(folds) == 4
    assert set(predictions["sporttery_handicap"]) == {-2, -1, 1, 2}
    assert payload["report"]["production_change_performed"] is False
    assert payload["report"]["deployment_gate"].startswith("blocked")
    assert payload["report"]["decision"] in {"research_candidate", "research_rejected"}
    assert payload["league_summaries"]
