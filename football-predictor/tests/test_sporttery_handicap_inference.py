from __future__ import annotations

import pandas as pd

from evaluate.sporttery_handicap_model import fit_final_margin_model
from models.sporttery_handicap_inference import predict_current_handicaps


def _training_matches() -> pd.DataFrame:
    rows = []
    for season_index, season in enumerate(("2020-21", "2021-22")):
        for index in range(60):
            margin = (index % 7) - 3
            rows.append(
                {
                    "match_id": f"{season}-{index}", "date": f"{2020 + season_index}-09-{index % 28 + 1:02d}",
                    "season": season, "league": "E0", "home_team": "A", "away_team": "B",
                    "home_goals": max(margin, 0) + 1, "away_goals": max(-margin, 0) + 1,
                    "AvgH": 2.0 + (index % 3) * 0.1, "AvgD": 3.3, "AvgA": 3.5,
                    "AHh": -0.5, "AvgAHH": 1.9, "AvgAHA": 1.95,
                    "Avg>2.5": 1.9, "Avg<2.5": 1.95,
                }
            )
    return pd.DataFrame(rows)


def _market() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2026-08-10", "match_id": "2026-08-10|001", "match_number": "001",
                "competition": "英超", "kickoff_time": "2026-08-10 20:00", "home_team": "曼城", "away_team": "阿森纳",
                "home_handicap": -1, "rqspf_odds_home": 2.8, "rqspf_odds_draw": 3.3, "rqspf_odds_away": 2.1,
            }
        ]
    )


def _external() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event_id": "e1", "date": "2026-08-10", "captured_at": "2026-08-10T11:00:00+08:00",
                "home_team": "Manchester City", "away_team": "Arsenal",
                "external_h2h_home_avg_odds": 1.8, "external_h2h_draw_avg_odds": 3.7, "external_h2h_away_avg_odds": 4.2,
                "external_home_spread_point": -0.75, "external_home_spread_avg_odds": 1.9, "external_away_spread_avg_odds": 1.95,
                "external_over_avg_odds": 1.88, "external_under_avg_odds": 1.98,
            }
        ]
    )


def test_controlled_inference_uses_safe_mapped_external_snapshot():
    model, _ = fit_final_margin_model(_training_matches())
    predictions, audit = predict_current_handicaps(
        _market(), _external(), model=model,
        metadata={"model_id": "test", "stable_handicaps": [-2, -1], "stable_weight": 0.25, "limited_weight": 0.1},
        analysis_at="2026-08-10 12:00",
    )
    assert audit["production_auxiliary"] == 1
    assert predictions.loc[0, "handicap_model_usage"] == "production_auxiliary"
    total = predictions.loc[0, [
        "handicap_blended_probability_home", "handicap_blended_probability_draw", "handicap_blended_probability_away"
    ]].astype(float).sum()
    assert abs(total - 1.0) < 1e-9


def test_inference_blocks_when_external_snapshot_is_missing():
    model, _ = fit_final_margin_model(_training_matches())
    predictions, audit = predict_current_handicaps(
        _market(), pd.DataFrame(), model=model,
        metadata={"model_id": "test"}, analysis_at="2026-08-10 12:00",
    )
    assert audit["blocked"] == 1
    assert predictions.loc[0, "handicap_model_reason"] == "no_safe_external_snapshot"
