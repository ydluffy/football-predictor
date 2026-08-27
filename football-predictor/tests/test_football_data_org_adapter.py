from __future__ import annotations

import pandas as pd

from world_cup.football_data_org_adapter import FootballDataOrgClient
from world_cup.football_data_org_adapter import import_football_data_world_cup
from world_cup.football_data_org_adapter import matches_payload_to_fixtures
from world_cup.football_data_org_adapter import teams_payload_to_tables


def test_football_data_matches_convert_to_fixtures():
    payload = {
        "matches": [
            {
                "id": 537327,
                "utcDate": "2026-06-11T19:00:00Z",
                "status": "FINISHED",
                "matchday": 1,
                "stage": "GROUP_STAGE",
                "group": "GROUP_A",
                "homeTeam": {"name": "Mexico"},
                "awayTeam": {"name": "South Africa"},
                "score": {
                    "winner": "HOME_TEAM",
                    "fullTime": {"home": 2, "away": 0},
                },
                "lastUpdated": "2026-06-26T07:48:25Z",
            }
        ]
    }

    fixtures = matches_payload_to_fixtures(payload)

    assert fixtures.loc[0, "match_id"] == "537327"
    assert fixtures.loc[0, "date"] == "2026-06-11"
    assert fixtures.loc[0, "home_team"] == "Mexico"
    assert fixtures.loc[0, "home_score"] == 2


def test_football_data_teams_convert_to_player_tables():
    payload = {
        "teams": [
            {
                "id": 758,
                "name": "Uruguay",
                "shortName": "Uruguay",
                "tla": "URU",
                "coach": {
                    "id": 56079,
                    "name": "Marcelo Bielsa",
                    "dateOfBirth": "1955-07-21",
                    "nationality": "Argentina",
                    "contract": {"start": None, "until": None},
                },
                "squad": [
                    {
                        "id": 28612,
                        "name": "Darwin Núñez",
                        "position": "Offence",
                        "dateOfBirth": "1999-06-24",
                    }
                ],
            }
        ]
    }

    tables = teams_payload_to_tables(payload, snapshot_date="2026-06-26")

    assert tables["teams"].loc[0, "team"] == "Uruguay"
    assert tables["coaches"].loc[0, "coach_name"] == "Marcelo Bielsa"
    assert tables["players"].loc[0, "player_id"] == "football_data_28612"
    assert tables["squads"].loc[0, "role"] == "squad"


def test_football_data_import_writes_empty_outputs_without_token(tmp_path):
    audit = import_football_data_world_cup(
        output_dir=tmp_path,
        season=2026,
        api_token="",
    )

    assert audit["status"] == "skipped"
    assert (tmp_path / "fixtures.csv").exists()
    assert (tmp_path / "coaches.csv").exists()
    assert pd.read_csv(tmp_path / "players.csv").empty


def test_explicit_empty_token_does_not_fall_back_to_environment(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_TOKEN", "environment-token")

    assert FootballDataOrgClient(api_token="").configured is False
    assert FootballDataOrgClient().api_token == "environment-token"
