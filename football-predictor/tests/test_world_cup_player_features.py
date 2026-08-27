from __future__ import annotations

import pandas as pd
import pytest

from world_cup.player_data import (
    PlayerDataBundle,
    load_availability,
    load_player_registry,
    load_squad_snapshots,
    resolve_player_id,
)
from world_cup.squad_features import (
    build_fixture_squad_features,
    build_team_squad_features,
)


def _bundle() -> PlayerDataBundle:
    players = pd.DataFrame(
        [
            {
                "player_id": player_id,
                "canonical_name": player_id.upper(),
                "national_team": team,
                "date_of_birth": pd.Timestamp("2000-01-01"),
            }
            for team, player_id in (
                ("A", "a1"),
                ("A", "a2"),
                ("A", "a3"),
                ("B", "b1"),
                ("B", "b2"),
            )
        ]
    )
    squads = pd.DataFrame(
        [
            {
                "snapshot_date": pd.Timestamp("2026-06-10"),
                "team": team,
                "player_id": player_id,
                "role": "starter",
                "position": "MF",
                "club": club,
            }
            for team, player_id, club in (
                ("A", "a1", "Club X"),
                ("A", "a2", "Club X"),
                ("A", "a3", "Club Y"),
                ("B", "b1", "Club Z"),
                ("B", "b2", "Club W"),
            )
        ]
    )
    availability = pd.DataFrame(
        [
            *[
                {
                    "as_of_date": pd.Timestamp("2026-06-14"),
                    "team": team,
                    "player_id": player_id,
                    "status": "available",
                    "reason": "",
                }
                for team, player_id in (
                    ("A", "a1"),
                    ("A", "a3"),
                    ("B", "b1"),
                    ("B", "b2"),
                )
            ],
            {
                "as_of_date": pd.Timestamp("2026-06-14"),
                "team": "A",
                "player_id": "a2",
                "status": "injured",
                "reason": "test",
            },
            {
                "as_of_date": pd.Timestamp("2026-06-16"),
                "team": "A",
                "player_id": "a1",
                "status": "injured",
                "reason": "future",
            },
        ]
    )
    club_rows = []
    for player_id in ("a1", "a2", "a3", "b1", "b2"):
        club_rows.extend(
            [
                {
                    "match_date": pd.Timestamp("2026-06-01"),
                    "player_id": player_id,
                    "club": "Club",
                    "competition": "League",
                    "minutes": 90,
                    "started": True,
                    "goals": 1,
                    "assists": 0,
                    "xg": 0.5,
                    "xa": 0.1,
                },
                {
                    "match_date": pd.Timestamp("2026-06-16"),
                    "player_id": player_id,
                    "club": "Club",
                    "competition": "League",
                    "minutes": 120,
                    "started": True,
                    "goals": 9,
                    "assists": 9,
                    "xg": 9.0,
                    "xa": 9.0,
                },
            ]
        )
    national = pd.DataFrame(
        [
            {
                "match_date": pd.Timestamp("2026-05-01"),
                "team": "A",
                "opponent": "B",
                "player_id": player_id,
                "started": True,
                "minutes": 90,
            }
            for player_id in ("a1", "a2")
        ]
        + [
            {
                "match_date": pd.Timestamp("2026-05-01"),
                "team": "B",
                "opponent": "A",
                "player_id": player_id,
                "started": True,
                "minutes": 90,
            }
            for player_id in ("b1", "b2")
        ]
    )
    return PlayerDataBundle(
        players=players,
        aliases=pd.DataFrame(),
        squads=squads,
        availability=availability,
        club_appearances=pd.DataFrame(club_rows),
        national_appearances=national,
    )


def test_player_registry_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "players.csv"
    pd.DataFrame(
        [
            {
                "player_id": "p1",
                "canonical_name": "One",
                "national_team": "A",
                "date_of_birth": "2000-01-01",
            },
            {
                "player_id": "p1",
                "canonical_name": "Two",
                "national_team": "A",
                "date_of_birth": "2001-01-01",
            },
        ]
    ).to_csv(path, index=False)

    with pytest.raises(ValueError, match="must be unique"):
        load_player_registry(path)


def test_squad_and_availability_reject_invalid_values(tmp_path):
    players = pd.DataFrame({"player_id": ["p1"]})
    squad_path = tmp_path / "squads.csv"
    pd.DataFrame(
        [
            {
                "snapshot_date": "2026-06-01",
                "team": "A",
                "player_id": "p1",
                "role": "captain",
                "position": "MF",
                "club": "Club",
            }
        ]
    ).to_csv(squad_path, index=False)
    with pytest.raises(ValueError, match="invalid roles"):
        load_squad_snapshots(squad_path, players)

    availability_path = tmp_path / "availability.csv"
    pd.DataFrame(
        [
            {
                "as_of_date": "2026-06-01",
                "team": "A",
                "player_id": "p1",
                "status": "maybe",
                "reason": "",
            }
        ]
    ).to_csv(availability_path, index=False)
    with pytest.raises(ValueError, match="invalid statuses"):
        load_availability(availability_path, players)


def test_player_identity_resolution_requires_unique_match():
    aliases = pd.DataFrame(
        [
            {
                "source": "provider",
                "source_player_id": "10",
                "source_name": "Player One",
                "player_id": "p1",
            }
        ]
    )

    assert (
        resolve_player_id(
            aliases,
            source="provider",
            source_player_id="10",
        )
        == "p1"
    )
    with pytest.raises(ValueError, match="not uniquely resolved"):
        resolve_player_id(
            aliases,
            source="provider",
            source_player_id="missing",
        )


def test_team_squad_features_use_only_pre_match_information():
    features = build_team_squad_features(
        _bundle(),
        team="A",
        as_of_date="2026-06-15",
    )

    assert features["expected_starters"] == 3
    assert features["starter_available_rate"] == pytest.approx(2 / 3)
    assert features["unavailable_players"] == 1
    assert features["starter_minutes_30"] == 270
    assert features["starter_goal_contributions_90"] == 1.0
    assert features["average_national_caps"] == pytest.approx(2 / 3)
    assert features["previous_lineup_retention"] == pytest.approx(2 / 3)
    assert features["same_club_starter_pairs"] == 1


def test_fixture_squad_features_build_home_away_and_differences():
    fixtures = pd.DataFrame(
        [{"date": "2026-06-15", "home_team": "A", "away_team": "B"}]
    )

    out = build_fixture_squad_features(_bundle(), fixtures)

    assert out.loc[0, "home_expected_starters"] == 3
    assert out.loc[0, "away_expected_starters"] == 2
    assert out.loc[0, "expected_starters_diff"] == 1
    assert out.loc[0, "starter_available_rate_diff"] < 0
