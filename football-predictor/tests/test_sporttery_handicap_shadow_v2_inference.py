from __future__ import annotations

import pandas as pd
import pytest

from evaluate.sporttery_handicap_model import fit_final_margin_model
from models.sporttery_handicap_shadow_v2_inference import predict_current_handicaps_shadow_v2


def _training_matches() -> pd.DataFrame:
    rows = []
    for season_index, season in enumerate(("2020-21", "2021-22")):
        for index in range(54):
            margin = (index % 7) - 3
            rows.append(
                {
                    "match_id": f"{season}-{index}", "date": f"{2020 + season_index}-09-{index % 28 + 1:02d}",
                    "season": season, "league": "E0", "home_team": "A", "away_team": "B",
                    "home_goals": max(margin, 0) + 1, "away_goals": max(-margin, 0) + 1,
                    "AvgH": 2.1, "AvgD": 3.3, "AvgA": 3.4, "AHh": -0.5,
                    "AvgAHH": 1.9, "AvgAHA": 1.95, "Avg>2.5": 1.9, "Avg<2.5": 1.95,
                }
            )
    return pd.DataFrame(rows)


def _market() -> pd.DataFrame:
    return pd.DataFrame([{
        "date": "2026-08-10", "match_id": "x", "match_number": "001", "competition": "英超",
        "kickoff_time": "2026-08-10 20:00", "home_team": "曼城", "away_team": "阿森纳",
        "home_handicap": -1, "rqspf_odds_home": 2.8, "rqspf_odds_draw": 3.3, "rqspf_odds_away": 2.1,
    }])


def _external() -> pd.DataFrame:
    return pd.DataFrame([{
        "date": "2026-08-10", "captured_at": "2026-08-10T11:00:00+08:00",
        "home_team": "Manchester City", "away_team": "Arsenal",
        "external_h2h_home_avg_odds": 1.8, "external_h2h_draw_avg_odds": 3.7, "external_h2h_away_avg_odds": 4.2,
        "external_home_spread_point": -0.75, "external_home_spread_avg_odds": 1.9, "external_away_spread_avg_odds": 1.95,
        "external_over_avg_odds": 1.88, "external_under_avg_odds": 1.98,
    }])


def test_shadow_inference_never_returns_production_usage():
    model, _ = fit_final_margin_model(_training_matches(), c=0.5)
    metadata = {
        "deployment_mode": "shadow_only", "model_id": "v2-test", "stable_handicaps": [-2, -1],
        "stable_weight": 0.5, "limited_weight": 0.25,
        "can_trigger_bet_alone": False, "can_write_production_ledger": False,
    }
    predictions, audit = predict_current_handicaps_shadow_v2(
        _market(), _external(), model=model, metadata=metadata, analysis_at="2026-08-10 12:00"
    )
    assert predictions.loc[0, "handicap_model_usage"] == "shadow_only"
    assert predictions.loc[0, "shadow_can_trigger_bet"] == False  # noqa: E712
    assert audit["shadow_eligible"] == 1
    assert audit["can_write_production_ledger"] is False


def test_shadow_inference_rejects_non_shadow_metadata():
    model, _ = fit_final_margin_model(_training_matches(), c=0.5)
    with pytest.raises(ValueError, match="shadow-only"):
        predict_current_handicaps_shadow_v2(
            _market(), _external(), model=model, metadata={"deployment_mode": "production"}
        )
