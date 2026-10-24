import pandas as pd

from data.api_football_prematch import build_api_football_match_mapping
from world_cup.api_football_adapter import api_fixture_rows_to_frame


def test_reviewed_ids_cannot_be_bypassed_by_identical_names():
    local = pd.DataFrame([dict(match_id="one", competition_id="UEFA_CHAMPIONS_LEAGUE",
        kickoff="2026-10-21T19:00:00Z", home_team="Lille", away_team="Galatasaray")])
    api = pd.DataFrame([dict(source_fixture_id="one", kickoff_time="2026-10-21T19:00:00Z",
        home_team="Lille", away_team="Galatasaray", source_home_team_id=79,
        source_away_team_id=645, league_id=2)])
    assert len(build_api_football_match_mapping(local, api)[0]) == 1
    for column, value in [("source_home_team_id", 999), ("source_away_team_id", 999), ("league_id", 140)]:
        invalid = api.copy()
        invalid[column] = value
        mapped, audit = build_api_football_match_mapping(local, invalid)
        assert mapped.empty
        assert audit["review_required"]
    assert len(build_api_football_match_mapping(local, api.drop(columns=["source_home_team_id", "source_away_team_id", "league_id"]))[0]) == 1


def test_adapter_preserves_source_identity():
    frame = api_fixture_rows_to_frame([dict(fixture=dict(id=1), teams=dict(
        home=dict(id=79, name="Lille"), away=dict(id=645, name="Galatasaray")))])
    assert frame.iloc[0].source_home_team_id == 79
    assert frame.iloc[0].source_away_team_id == 645
