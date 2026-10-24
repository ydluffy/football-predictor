import pandas as pd
import pytest

from data.api_football_prematch import build_api_football_match_mapping


# Names and fixture IDs from the archived 2026-10-21 provider response.
PAIRS = [
    ("里尔", "加拉塔萨", "Lille", "Galatasaray", "1635684"),
    ("维拉", "维京", "Aston Villa", "Viking", "1635621"),
    ("贝蒂斯", "费耶诺德", "Real Betis", "Feyenoord", "1635636"),
    ("里斯本", "LASK林茨", "Sporting CP", "Lask Linz", "1635737"),
    ("布鲁日", "朗斯", "Club Brugge KV", "Lens", "1635645"),
    ("帕梅拉斯", "弗鲁米嫩", "Palmeiras", "Fluminense", "1640021"),
]


@pytest.mark.parametrize("home,away,api_home,api_away,fid", PAIRS)
def test_verified_aliases_preserve_matching_guards(home, away, api_home, api_away, fid):
    local = pd.DataFrame([dict(match_id="local", competition_id="UNKNOWN",
        kickoff="2026-10-22T03:00:00+08:00", home_team=home, away_team=away,
        home_team_canonical=home, away_team_canonical=away)])
    api = pd.DataFrame([dict(source_fixture_id=fid,
        kickoff_time="2026-10-21T19:00:00Z", home_team=api_home, away_team=api_away)])
    mapped, audit = build_api_football_match_mapping(local, api)
    assert mapped.source_fixture_id.tolist() == [fid]
    assert audit["unmatched_match_ids"] == []
    for column, value in [("home_team", api_home + " W"),
                          ("away_team", "Unrelated team"),
                          ("kickoff_time", "2026-10-21T20:00:00Z")]:
        invalid = api.copy()
        invalid[column] = value
        assert build_api_football_match_mapping(local, invalid)[0].empty
    duplicate = pd.concat([api, api.assign(source_fixture_id="other")], ignore_index=True)
    mapped, audit = build_api_football_match_mapping(local, duplicate)
    assert mapped.empty
    assert audit["ambiguous_match_ids"] == ["local"]
