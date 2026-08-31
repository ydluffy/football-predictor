from __future__ import annotations

import pandas as pd

from world_cup.lineup_adjustment import build_fixture_lineup_adjustments
from world_cup.player_data import PlayerDataBundle
from world_cup.model import WorldCupBaselineModel


def _bundle(starters: bool = True) -> PlayerDataBundle:
    players = []
    squads = []
    availability = []
    national = []
    for team in ("A", "B"):
        for index in range(1, 12):
            player_id = f"{team}{index}"
            players.append(
                {
                    "player_id": player_id,
                    "canonical_name": player_id,
                    "national_team": team,
                    "date_of_birth": pd.Timestamp("2000-01-01"),
                }
            )
            squads.append(
                {
                    "snapshot_date": pd.Timestamp("2026-06-15"),
                    "team": team,
                    "player_id": player_id,
                    "role": "starter" if starters else "squad",
                    "position": "MF",
                    "club": "",
                }
            )
            availability.append(
                {
                    "as_of_date": pd.Timestamp("2026-06-15"),
                    "team": team,
                    "player_id": player_id,
                    "status": "available",
                    "reason": "",
                }
            )
            if team == "A":
                national.append(
                    {
                        "match_date": pd.Timestamp("2026-06-01"),
                        "team": team,
                        "opponent": "B",
                        "player_id": player_id,
                        "started": True,
                        "minutes": 90,
                    }
                )
    return PlayerDataBundle(
        players=pd.DataFrame(players),
        aliases=pd.DataFrame(),
        squads=pd.DataFrame(squads),
        availability=pd.DataFrame(availability),
        club_appearances=pd.DataFrame(
            columns=[
                "match_date",
                "player_id",
                "club",
                "competition",
                "minutes",
                "started",
                "goals",
                "assists",
                "xg",
                "xa",
            ]
        ),
        national_appearances=pd.DataFrame(national),
    )


def test_lineup_adjustment_is_inactive_without_confirmed_lineups():
    fixtures = pd.DataFrame([{"date": "2026-06-16", "home_team": "A", "away_team": "B"}])
    out = build_fixture_lineup_adjustments(_bundle(starters=False), fixtures)

    assert out.loc[0, "lineup_adjustment_active"] == 0.0
    assert out.loc[0, "home_goal_multiplier"] == 1.0
    assert out.loc[0, "away_goal_multiplier"] == 1.0


def test_confirmed_lineup_can_shift_goal_multipliers_conservatively():
    fixtures = pd.DataFrame([{"date": "2026-06-16", "home_team": "A", "away_team": "B"}])
    out = build_fixture_lineup_adjustments(_bundle(starters=True), fixtures)

    assert out.loc[0, "lineup_adjustment_active"] == 1.0
    assert out.loc[0, "home_goal_multiplier"] > 1.0
    assert out.loc[0, "away_goal_multiplier"] < 1.0


def test_model_accepts_lineup_goal_multipliers():
    matches = pd.DataFrame(
        [
            {
                "home_team": "A",
                "away_team": "B",
                "home_goals": 1,
                "away_goals": 1,
            }
        ]
    )
    model = WorldCupBaselineModel().fit(matches)
    base = model.predict_match("A", "B")
    adjusted = model.predict_match("A", "B", home_goal_multiplier=1.1, away_goal_multiplier=0.9)

    assert adjusted["expected_home_goals"] > base["expected_home_goals"]
    assert adjusted["expected_away_goals"] < base["expected_away_goals"]
