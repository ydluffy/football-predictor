from __future__ import annotations

import numpy as np
import pandas as pd

from evaluate.sporttery_handicap_shadow_v2 import (
    blend_probabilities,
    run_sporttery_handicap_shadow_v2,
)


def _matches() -> pd.DataFrame:
    rows = []
    margins = [-2, -1, 0, 1, 2, 3]
    for season_index, season in enumerate(("2019-20", "2020-21", "2021-22", "2022-23")):
        for index in range(48):
            margin = margins[index % len(margins)]
            rows.append(
                {
                    "match_id": f"v2-{season}-{index}",
                    "date": f"{2019 + season_index}-09-{index % 28 + 1:02d}",
                    "season": season,
                    "league": "E0",
                    "home_team": f"H{index % 8}",
                    "away_team": f"A{index % 8}",
                    "home_goals": max(margin, 0) + 1,
                    "away_goals": max(-margin, 0) + 1,
                    "AvgH": 2.2,
                    "AvgD": 3.2,
                    "AvgA": 3.1,
                    "AHh": -0.25 * margin,
                    "AvgAHH": 1.9,
                    "AvgAHA": 1.95,
                    "Avg>2.5": 1.9,
                    "Avg<2.5": 1.95,
                }
            )
    return pd.DataFrame(rows)


def test_blend_probabilities_is_normalized_and_respects_zero_weight():
    baseline = np.array([[0.2, 0.3, 0.5]])
    candidate = np.array([[0.5, 0.3, 0.2]])
    assert np.allclose(blend_probabilities(baseline, candidate, 0.0), baseline)
    assert np.allclose(blend_probabilities(baseline, candidate, 0.5).sum(axis=1), [1.0])


def test_shadow_v2_uses_only_prior_seasons_and_never_changes_production():
    predictions, folds, payload = run_sporttery_handicap_shadow_v2(
        _matches(), min_train_seasons=2, n_bootstrap=100
    )
    assert predictions["match_id"].nunique() == 96
    assert set(folds["holdout_season"]) == {"2021-22", "2022-23"}
    assert folds["selected_alpha"].between(0.0, 0.5).all()
    assert payload["report"]["mode"] == "shadow_only"
    assert payload["report"]["production_change_performed"] is False
    assert payload["report"]["deployment_gate"].startswith("blocked")
    assert payload["alpha_audit"]
