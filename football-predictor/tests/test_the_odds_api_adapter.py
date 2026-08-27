from __future__ import annotations

import pandas as pd

from world_cup.the_odds_api_adapter import TheOddsApiClient
from world_cup.the_odds_api_adapter import import_the_odds_api_world_cup
from world_cup.the_odds_api_adapter import find_the_odds_api_h2h
from world_cup.the_odds_api_adapter import index_the_odds_api_h2h
from world_cup.the_odds_api_adapter import odds_payload_to_frame
from world_cup.the_odds_api_adapter import summarize_odds_frame


def test_the_odds_api_payload_converts_to_long_odds_and_summary():
    payload = [
        {
            "id": "evt_1",
            "sport_key": "soccer_fifa_world_cup",
            "sport_title": "FIFA World Cup",
            "commence_time": "2026-06-27T15:00:00Z",
            "home_team": "Germany",
            "away_team": "Ecuador",
            "bookmakers": [
                {
                    "key": "book_a",
                    "title": "Book A",
                    "last_update": "2026-06-27T08:00:00Z",
                    "markets": [
                        {
                            "key": "h2h",
                            "last_update": "2026-06-27T08:00:00Z",
                            "outcomes": [
                                {"name": "Germany", "price": 1.5},
                                {"name": "Draw", "price": 4.2},
                                {"name": "Ecuador", "price": 6.0},
                            ],
                        },
                        {
                            "key": "totals",
                            "last_update": "2026-06-27T08:00:00Z",
                            "outcomes": [
                                {"name": "Over", "price": 1.9, "point": 2.5},
                                {"name": "Under", "price": 1.95, "point": 2.5},
                            ],
                        },
                        {
                            "key": "spreads",
                            "last_update": "2026-06-27T08:00:00Z",
                            "outcomes": [
                                {"name": "Germany", "price": 2.05, "point": -1.5},
                                {"name": "Ecuador", "price": 1.8, "point": 1.5},
                            ],
                        },
                    ],
                },
                {
                    "key": "book_b",
                    "title": "Book B",
                    "last_update": "2026-06-27T08:02:00Z",
                    "markets": [
                        {
                            "key": "h2h",
                            "last_update": "2026-06-27T08:02:00Z",
                            "outcomes": [
                                {"name": "Germany", "price": 1.55},
                                {"name": "Draw", "price": 4.0},
                                {"name": "Ecuador", "price": 5.8},
                            ],
                        }
                    ],
                },
            ],
        }
    ]

    odds = odds_payload_to_frame(payload)
    summary = summarize_odds_frame(odds)
    h2h = summary[summary["market_key"].eq("h2h")].iloc[0]
    totals = summary[summary["market_key"].eq("totals")].iloc[0]
    spreads = summary[summary["market_key"].eq("spreads")]

    assert len(odds) == 10
    assert set(odds["outcome_label"]) == {"home", "draw", "away", "over", "under", "home_spread", "away_spread"}
    assert h2h["bookmaker_count"] == 2
    assert h2h["home_best_odds"] == 1.55
    assert 0 < h2h["home_market_probability"] < 1
    assert totals["point"] == 2.5
    assert totals["over_avg_odds"] == 1.9
    assert spreads["home_spread_avg_odds"].notna().any()
    assert spreads["away_spread_avg_odds"].notna().any()

    index = index_the_odds_api_h2h(summary)
    match = find_the_odds_api_h2h(
        index,
        date="2026-06-27",
        home_team="Germany",
        away_team="Ecuador",
    )
    assert match["event_id"] == "evt_1"
    assert match["bookmaker_count"] == 2


def test_the_odds_api_import_writes_empty_outputs_without_key(tmp_path):
    audit = import_the_odds_api_world_cup(
        output_dir=tmp_path,
        api_key="",
    )

    assert audit["status"] == "skipped"
    assert (tmp_path / "odds.csv").exists()
    assert (tmp_path / "match_market_summary.csv").exists()
    assert pd.read_csv(tmp_path / "odds.csv").empty


def test_explicit_empty_key_does_not_fall_back_to_environment(monkeypatch):
    monkeypatch.setenv("THE_ODDS_API_KEY", "environment-key")

    assert TheOddsApiClient(api_key="").configured is False
    assert TheOddsApiClient().api_key == "environment-key"
