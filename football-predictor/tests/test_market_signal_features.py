from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_market_signal_features.py"
SPEC = importlib.util.spec_from_file_location("build_market_signal_features", MODULE_PATH)
signals = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = signals
SPEC.loader.exec_module(signals)


def test_missing_external_market_is_unknown_not_high_risk():
    markets = pd.DataFrame(
        [
            {
                "date": "2026-07-18",
                "match_number": "201",
                "league": "瑞超",
                "home_team": "哥德堡",
                "away_team": "布鲁马波",
                "home_handicap": -1,
                "spf_odds_home": 1.50,
                "spf_odds_draw": 3.80,
                "spf_odds_away": 5.00,
            }
        ]
    )

    features = signals.build_market_signal_features(markets, pd.DataFrame(), pd.DataFrame())

    assert features.loc[0, "inner_outer_line_relation"] == "missing_external"
    assert features.loc[0, "market_risk_flags"] == "no_external_market"
    assert features.loc[0, "market_signal_strength"] == "medium_unknown"


def test_sporttery_deeper_than_external_is_high_risk():
    markets = pd.DataFrame(
        [
            {
                "date": "2026-07-19",
                "match_number": "103",
                "league": "世界杯",
                "home_team": "法国",
                "away_team": "英格兰",
                "home_handicap": -1,
                "spf_odds_home": 1.70,
                "spf_odds_draw": 3.80,
                "spf_odds_away": 3.60,
            }
        ]
    )
    external_history = pd.DataFrame(
        [
            {
                "date": "2026-07-19",
                "captured_at": "2026-07-17T14:20:00+08:00",
                "home_team": "France",
                "away_team": "England",
                "external_h2h_favorite": "home",
                "external_h2h_favorite_probability": 0.50,
                "external_home_spread_point": -0.5,
                "external_line_label": "半球",
                "external_line_bucket": "shallow",
                "external_spread_favorite": "home",
                "external_total_signal": "over",
            }
        ]
    )
    external_history["home_key"] = external_history["home_team"].map(signals.team_key)
    external_history["away_key"] = external_history["away_team"].map(signals.team_key)

    features = signals.build_market_signal_features(markets, pd.DataFrame(), external_history)

    assert features.loc[0, "inner_outer_home_line_gap"] == 0.5
    assert features.loc[0, "inner_outer_line_relation"] == "sporttery_deeper_home"
    assert "sporttery_deeper_than_external" in features.loc[0, "market_risk_flags"]
    assert features.loc[0, "market_signal_strength"] == "high_risk"
