from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "backtest_market_movement_value.py"
SPEC = importlib.util.spec_from_file_location("backtest_market_movement_value", MODULE_PATH)
backtest = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = backtest
SPEC.loader.exec_module(backtest)


def test_cover_helpers():
    assert backtest.rqspf_cover_result(3, 0, -1) == "home_cover"
    assert backtest.rqspf_cover_result(2, 1, -1) == "push"
    assert backtest.rqspf_cover_result(1, 2, 1) == "push"
    assert backtest.favorite_cover_from_result("away_cover", "away") == "cover"
    assert backtest.favorite_cover_from_result("home_cover", "away") == "fail"


def test_build_external_movement_uses_opening_and_latest():
    history = pd.DataFrame(
        [
            {
                "date": "2026-07-18",
                "captured_at": "2026-07-17T03:00:00+00:00",
                "home_team": "France",
                "away_team": "England",
                "external_h2h_favorite": "home",
                "external_h2h_favorite_probability": 0.40,
                "external_home_spread_point": 0.0,
                "external_total_point": 2.5,
            },
            {
                "date": "2026-07-18",
                "captured_at": "2026-07-17T12:00:00+00:00",
                "home_team": "France",
                "away_team": "England",
                "external_h2h_favorite": "home",
                "external_h2h_favorite_probability": 0.45,
                "external_home_spread_point": -0.25,
                "external_total_point": 2.5,
            },
        ]
    )

    movement = backtest.build_external_movement(history)

    assert len(movement) == 1
    assert movement.loc[0, "external_snapshot_count"] == 2
    assert movement.loc[0, "external_favorite_probability_delta"] == pytest.approx(0.05)
    assert movement.loc[0, "external_home_spread_point_delta"] == -0.25


def test_build_dataset_marks_sporttery_cover():
    sporttery_history = pd.DataFrame(
        [
            {
                "date": "2026-07-18",
                "match_id": "",
                "match_number": "201",
                "home_team": "France",
                "away_team": "England",
                "snapshot_type": "open",
                "home_handicap": -1,
                "captured_at": "2026-07-17T03:00:00+00:00",
            }
        ]
    )
    results = pd.DataFrame(
        [
            {
                "date": "2026-07-18",
                "match_number": "201",
                "home_team": "France",
                "away_team": "England",
                "full_time_score": "2:0",
                "home_key": "france",
                "away_key": "england",
                "home_goals": 2,
                "away_goals": 0,
                "actual_spf": "home",
                "actual_total_goals": 2,
            }
        ]
    )
    dataset = backtest.build_dataset(sporttery_history, pd.DataFrame(), results)

    assert len(dataset) == 1
    assert dataset.loc[0, "sporttery_latest_favorite"] == "home"
    assert dataset.loc[0, "sporttery_favorite_cover"] == "cover"
