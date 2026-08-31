from __future__ import annotations

import json

from world_cup.player_data import load_player_data_bundle
from world_cup.statsbomb_adapter import (
    _position_minutes,
    convert_statsbomb_to_player_contract,
)


def test_position_minutes_from_statsbomb_segments():
    positions = [
        {
            "from": "00:00",
            "to": "64:10",
        },
        {
            "from": "70:00",
            "to": "90:00",
        },
    ]

    assert _position_minutes(positions) == 84 + 10 / 60

    overlapping = [
        {"from": "00:00", "to": "60:00"},
        {"from": "30:00", "to": "90:00"},
    ]
    assert _position_minutes(overlapping) == 90


def test_convert_statsbomb_lineup_to_contract(tmp_path):
    cache = tmp_path / "cache"
    (cache / "matches").mkdir(parents=True)
    (cache / "lineups").mkdir(parents=True)
    match = {
        "match_id": 1,
        "match_date": "2022-12-01",
        "home_team": {"home_team_name": "Canada"},
        "away_team": {"away_team_name": "Morocco"},
    }
    lineup = [
        {
            "team_name": "Canada",
            "lineup": [
                {
                    "player_id": 10,
                    "player_name": "Player One",
                    "positions": [
                        {
                            "position": "Center Forward",
                            "from": "00:00",
                            "to": "90:00",
                            "start_reason": "Starting XI",
                        }
                    ],
                }
            ],
        },
        {
            "team_name": "Morocco",
            "lineup": [
                {
                    "player_id": 20,
                    "player_name": "Player Two",
                    "positions": [
                        {
                            "position": "Goalkeeper",
                            "from": "45:00",
                            "to": "90:00",
                            "start_reason": "Substitution - On",
                        }
                    ],
                }
            ],
        },
    ]
    (cache / "matches" / "43_106.json").write_text(
        json.dumps([match]),
        encoding="utf-8",
    )
    (cache / "lineups" / "1.json").write_text(
        json.dumps(lineup),
        encoding="utf-8",
    )

    audit = convert_statsbomb_to_player_contract(cache, tmp_path / "output")
    bundle = load_player_data_bundle(tmp_path / "output")

    assert audit["players"] == 2
    assert len(bundle.squads) == 2
    assert bundle.squads.set_index("player_id").loc["statsbomb_10", "role"] == "starter"
    appearances = bundle.national_appearances.set_index("player_id")
    assert appearances.loc["statsbomb_10", "minutes"] == 90
    assert appearances.loc["statsbomb_20", "minutes"] == 45
    assert bundle.availability.empty
    assert bundle.club_appearances.empty
