from __future__ import annotations

from world_cup.espn_live_adapter import parse_match_summary, parse_team_roster


def _athlete(player_id: int, name: str) -> dict:
    return {
        "id": str(player_id),
        "displayName": name,
        "dateOfBirth": "2000-01-02T00:00Z",
        "position": {"displayName": "Midfielder"},
    }


def test_team_roster_is_squad_not_assumed_starting_lineup():
    payload = {
        "team": {"displayName": "Spain"},
        "athletes": [
            {
                **_athlete(1, "Player One"),
                "defaultTeam": {
                    "$ref": "http://sports.core.api.espn.pvt/v2/sports/soccer/teams/359?lang=en&region=us"
                },
                "defaultLeague": {
                    "$ref": "http://sports.core.api.espn.pvt/v2/sports/soccer/leagues/eng.1?lang=en&region=us"
                },
            }
        ],
    }
    players, aliases, squads, affiliations = parse_team_roster(
        payload,
        snapshot_date="2026-06-15",
    )
    assert players[0]["date_of_birth"] == "2000-01-02"
    assert aliases[0]["source"] == "espn_public"
    assert squads[0]["role"] == "squad"
    assert squads[0]["club"] == "eng.1:359"
    assert affiliations[0]["league_slug"] == "eng.1"


def test_team_roster_does_not_treat_national_team_as_club():
    payload = {
        "team": {"displayName": "Spain"},
        "athletes": [
            {
                **_athlete(1, "Player One"),
                "defaultTeam": {
                    "$ref": "http://sports.core.api.espn.pvt/v2/sports/soccer/teams/164?lang=en&region=us"
                },
                "defaultLeague": {
                    "$ref": "http://sports.core.api.espn.pvt/v2/sports/soccer/leagues/fifa.world?lang=en&region=us"
                },
            }
        ],
    }
    _, _, squads, affiliations = parse_team_roster(
        payload,
        snapshot_date="2026-06-15",
    )
    assert squads[0]["club"] == ""
    assert affiliations[0]["club_id"] == ""


def test_summary_requires_exactly_11_starters_before_confirming_lineup():
    entries = [
        {
            "starter": index < 10,
            "athlete": _athlete(index, f"Player {index}"),
            "position": {"displayName": "Midfielder"},
        }
        for index in range(1, 27)
    ]
    payload = {
        "header": {
            "competitions": [
                {
                    "date": "2026-06-15T12:00Z",
                    "status": {"type": {"completed": False}},
                    "competitors": [
                        {"team": {"id": "1", "displayName": "Spain"}},
                        {"team": {"id": "2", "displayName": "Cape Verde"}},
                    ],
                }
            ]
        },
        "rosters": [
            {
                "team": {"id": "1", "displayName": "Spain"},
                "roster": entries,
            }
        ],
    }
    parsed = parse_match_summary(payload, fetched_date="2026-06-15")
    assert {row["role"] for row in parsed["squads"]} == {"squad"}
    assert parsed["availability"] == []


def test_summary_only_records_explicit_injury_reports():
    payload = {
        "header": {
            "competitions": [
                {
                    "date": "2026-06-15T12:00Z",
                    "status": {"type": {"completed": False}},
                    "competitors": [
                        {"team": {"id": "1", "displayName": "Spain"}},
                        {"team": {"id": "2", "displayName": "Cape Verde"}},
                    ],
                }
            ]
        },
        "injuries": [
            {
                "team": {"id": "1"},
                "injuries": [
                    {
                        "athlete": _athlete(9, "Player Nine"),
                        "status": "Out",
                        "description": "Hamstring",
                    }
                ],
            }
        ],
    }
    parsed = parse_match_summary(payload, fetched_date="2026-06-15")
    assert parsed["availability"] == [
        {
            "as_of_date": "2026-06-15",
            "team": "Spain",
            "player_id": "espn_9",
            "status": "injured",
            "reason": "Hamstring",
        }
    ]
