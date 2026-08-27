from __future__ import annotations

import pandas as pd

from world_cup.espn_club_stats_adapter import parse_club_roster_stats
from world_cup.player_strength import apply_club_season_stats


def test_parse_club_roster_stats_extracts_season_totals():
    payload = {
        "season": {"displayName": "2026 MLS"},
        "team": {"displayName": "Inter Miami CF"},
        "athletes": [
            {
                "id": "10",
                "displayName": "Player One",
                "statistics": {
                    "splits": {
                        "categories": [
                            {
                                "stats": [
                                    {"name": "appearances", "value": 12},
                                    {"name": "subIns", "value": 2},
                                    {"name": "totalGoals", "value": 5},
                                    {"name": "goalAssists", "value": 4},
                                    {"name": "shotsOnTarget", "value": 11},
                                ]
                            }
                        ]
                    }
                },
            }
        ],
    }

    rows = parse_club_roster_stats(payload, club_id="usa.1:20232", league_slug="usa.1")

    assert rows[0]["player_id"] == "espn_10"
    assert rows[0]["starts_proxy"] == 10
    assert rows[0]["goals"] == 5
    assert rows[0]["assists"] == 4


def test_club_season_stats_blend_into_strengths():
    strengths = pd.DataFrame(
        [
            {
                "player_id": "p1",
                "national_team": "A",
                "player_strength_score": 0.2,
                "player_strength_confidence": 0.0,
            },
            {
                "player_id": "p2",
                "national_team": "A",
                "player_strength_score": 0.2,
                "player_strength_confidence": 0.0,
            },
        ]
    )
    stats = pd.DataFrame(
        [
            {
                "player_id": "p1",
                "appearances": 20,
                "starts_proxy": 18,
                "goals": 8,
                "assists": 5,
                "shots_on_target": 20,
            }
        ]
    )

    out = apply_club_season_stats(strengths, stats).set_index("player_id")

    assert out.loc["p1", "player_strength_score"] > out.loc["p2", "player_strength_score"]
    assert out.loc["p1", "player_strength_confidence"] > 0
