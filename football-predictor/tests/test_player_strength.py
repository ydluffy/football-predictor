from __future__ import annotations

import pandas as pd

from world_cup.lineup_adjustment import build_fixture_lineup_adjustments
from world_cup.player_data import PlayerDataBundle
from world_cup.player_strength import build_player_strengths


def _bundle() -> PlayerDataBundle:
    players = []
    squads = []
    for team in ("A", "B"):
        for index in range(1, 12):
            player_id = f"{team.lower()}{index}"
            players.append(
                {
                    "player_id": player_id,
                    "canonical_name": player_id,
                    "national_team": team,
                    "date_of_birth": pd.Timestamp("1998-01-01"),
                    "primary_position": "Forward",
                }
            )
            squads.append(
                {
                    "snapshot_date": pd.Timestamp("2026-06-15"),
                    "team": team,
                    "player_id": player_id,
                    "role": "starter",
                    "position": "Forward",
                    "club": "",
                }
            )
    players.append(
        {
            "player_id": "a12",
            "canonical_name": "bench",
            "national_team": "A",
            "date_of_birth": pd.Timestamp("1998-01-01"),
            "primary_position": "Forward",
        }
    )
    squads.append(
        {
            "snapshot_date": pd.Timestamp("2026-06-15"),
            "team": "A",
            "player_id": "a12",
            "role": "substitute",
            "position": "Forward",
            "club": "",
        }
    )
    players = pd.DataFrame(players)
    squads = pd.DataFrame(squads)
    national = pd.DataFrame(
        [
            {
                "match_date": pd.Timestamp("2026-06-10"),
                "team": "A",
                "opponent": "B",
                "player_id": "a1",
                "started": True,
                "minutes": 90,
            }
        ]
    )
    empty_club = pd.DataFrame(
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
    )
    return PlayerDataBundle(
        players=players,
        aliases=pd.DataFrame(),
        squads=squads,
        availability=pd.DataFrame(
            columns=["as_of_date", "team", "player_id", "status", "reason"]
        ),
        club_appearances=empty_club,
        national_appearances=national,
    )


def test_player_strength_uses_national_appearance_evidence():
    strengths = build_player_strengths(_bundle(), as_of_date="2026-06-16")
    indexed = strengths.set_index("player_id")

    assert indexed.loc["a1", "player_strength_confidence"] > 0
    assert indexed.loc["a12", "player_strength_confidence"] == 0
    assert indexed.loc["a1", "relative_player_strength"] > indexed.loc["a12", "relative_player_strength"]


def test_lineup_adjustment_accepts_player_strength_features():
    bundle = _bundle()
    strengths = build_player_strengths(bundle, as_of_date="2026-06-16")
    fixtures = pd.DataFrame([{"date": "2026-06-16", "home_team": "A", "away_team": "B"}])
    out = build_fixture_lineup_adjustments(
        bundle,
        fixtures,
        player_strengths=strengths,
    )

    assert "home_lineup_relative_strength" in out.columns
    assert out.loc[0, "home_lineup_relative_strength"] > 0
