from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "research_inner_outer_market_patterns.py"
SPEC = importlib.util.spec_from_file_location("research_inner_outer_market_patterns", MODULE_PATH)
research = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = research
SPEC.loader.exec_module(research)


def test_line_labels_and_settlement_helpers():
    assert research.line_label(0) == "平手"
    assert research.line_label(-0.5) == "半球"
    assert research.line_label(-1) == "一球"
    assert research.line_label(-1.5) == "球半"
    assert research.line_bucket(-1.5) == "one_and_half"

    assert research.spread_result(2, 1, -1) == "push"
    assert research.spread_result(3, 1, -1.5) == "home_cover"
    assert research.spread_result(1, 2, 0.5) == "away_cover"
    assert research.total_result(3, 2.5) == "over"
    assert research.total_result(2, 2.5) == "under"


def test_external_features_pair_spreads_and_totals():
    odds = pd.DataFrame(
        [
            {"event_id": "e1", "date": "2026-07-15", "commence_time": "2026-07-15T19:00:00Z", "home_team": "England", "away_team": "Argentina", "bookmaker_key": "a", "market_key": "h2h", "outcome_label": "home", "price": 2.0, "point": ""},
            {"event_id": "e1", "date": "2026-07-15", "commence_time": "2026-07-15T19:00:00Z", "home_team": "England", "away_team": "Argentina", "bookmaker_key": "a", "market_key": "h2h", "outcome_label": "draw", "price": 3.0, "point": ""},
            {"event_id": "e1", "date": "2026-07-15", "commence_time": "2026-07-15T19:00:00Z", "home_team": "England", "away_team": "Argentina", "bookmaker_key": "a", "market_key": "h2h", "outcome_label": "away", "price": 4.0, "point": ""},
            {"event_id": "e1", "date": "2026-07-15", "commence_time": "2026-07-15T19:00:00Z", "home_team": "England", "away_team": "Argentina", "bookmaker_key": "a", "market_key": "spreads", "outcome_label": "home_spread", "price": 1.8, "point": -0.5},
            {"event_id": "e1", "date": "2026-07-15", "commence_time": "2026-07-15T19:00:00Z", "home_team": "England", "away_team": "Argentina", "bookmaker_key": "a", "market_key": "spreads", "outcome_label": "away_spread", "price": 2.0, "point": 0.5},
            {"event_id": "e1", "date": "2026-07-15", "commence_time": "2026-07-15T19:00:00Z", "home_team": "England", "away_team": "Argentina", "bookmaker_key": "a", "market_key": "totals", "outcome_label": "over", "price": 1.7, "point": 2.5},
            {"event_id": "e1", "date": "2026-07-15", "commence_time": "2026-07-15T19:00:00Z", "home_team": "England", "away_team": "Argentina", "bookmaker_key": "a", "market_key": "totals", "outcome_label": "under", "price": 2.1, "point": 2.5},
        ]
    )

    features = research.build_external_features(odds)
    row = features.iloc[0]

    assert row["external_h2h_favorite"] == "home"
    assert row["external_home_spread_point"] == -0.5
    assert row["external_line_label"] == "半球"
    assert row["external_spread_favorite"] == "home"
    assert row["external_total_signal"] == "over"
