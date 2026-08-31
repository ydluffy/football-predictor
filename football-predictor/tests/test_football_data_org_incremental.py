from __future__ import annotations

import json

import pandas as pd

from data.football_data_org_incremental import build_v2_result_supplement, import_europe_incremental, normalize_matches
from data.football_data_org_results import build_sporttery_result_fallback


def _payload(status: str = "FINISHED") -> dict:
    return {
        "matches": [{
            "id": 123, "utcDate": "2026-08-16T16:00:00Z", "status": status,
            "matchday": 1, "stage": "REGULAR_SEASON",
            "competition": {"code": "PL"}, "season": {"startDate": "2026-08-01"},
            "homeTeam": {"id": 1, "name": "Alpha FC"},
            "awayTeam": {"id": 2, "name": "Beta FC"},
            "score": {"winner": "HOME_TEAM", "halfTime": {"home": 1, "away": 0},
                      "fullTime": {"home": 2, "away": 1}},
        }]
    }


class FakeClient:
    def __init__(self) -> None:
        self.calls = []
        self.last_headers = {"X-Requests-Available-Minute": "9"}

    def get(self, path, params=None):
        self.calls.append((path, params))
        return _payload() if path == "matches" else {"season": {}, "standings": []}


def test_incremental_archive_is_idempotent_and_date_to_is_exclusive(tmp_path):
    client = FakeClient()
    kwargs = dict(client=client, date_from="2026-08-16", date_to="2026-08-16",
                  competitions=["PL"], captured_at="2026-08-16T12:00:00+08:00",
                  output_root=tmp_path, include_standings=False)
    first = import_europe_incremental(**kwargs)
    second = import_europe_incremental(**kwargs)

    assert client.calls[0][1]["dateTo"] == "2026-08-17"
    assert first["snapshot_id"] == second["snapshot_id"]
    assert len(list((tmp_path / "raw").rglob("*.json"))) == 1
    assert len(pd.read_csv(tmp_path / "matches_history.csv")) == 1


def test_v2_export_is_explicit_result_supplement():
    matches = normalize_matches(_payload(), snapshot_id="s1", captured_at="2026-08-16T12:00:00+08:00")
    result = build_v2_result_supplement(matches)

    assert result.loc[0, "actual_result"] == "H"
    assert result.loc[0, "home_goals"] == 2
    assert "spf_odds_home" not in result.columns


def test_result_fallback_requires_unique_time_and_team_mapping():
    scan = pd.DataFrame([{
        "match_id": "2026-08-16|001", "match_number": "001", "competition": "英超",
        "competition_id": "ENG_PREMIER_LEAGUE", "kickoff": "2026-08-17T00:00:00+08:00",
        "home_team": "Alpha FC", "away_team": "Beta FC",
    }])
    matches = normalize_matches(_payload(), snapshot_id="s1", captured_at="2026-08-16T12:00:00+08:00")
    markets = pd.DataFrame([{"match_number": "001", "home_handicap": -1,
                             "spf_odds_home": 1.8, "spf_odds_draw": 3.4, "spf_odds_away": 4.2}])
    results, mapping, audit = build_sporttery_result_fallback(
        scan_fixtures=scan, football_matches=matches, official_markets=markets,
    )

    assert len(mapping) == 1
    assert audit["result_rows"] == 1
    assert results.loc[0, "full_time_score"] == "2:1"
    assert results.loc[0, "rqspf_result"] == "让平"


def test_unmatched_result_never_reaches_settlement_output():
    scan = pd.DataFrame([{
        "match_id": "x", "match_number": "001", "competition": "英超",
        "competition_id": "ENG_PREMIER_LEAGUE", "kickoff": "2026-08-17T00:00:00+08:00",
        "home_team": "Different", "away_team": "Beta FC",
    }])
    matches = normalize_matches(_payload(), snapshot_id="s1", captured_at="2026-08-16T12:00:00+08:00")
    results, _, audit = build_sporttery_result_fallback(
        scan_fixtures=scan, football_matches=matches, official_markets=pd.DataFrame(columns=["match_number"]),
    )

    assert results.empty
    assert audit["unmatched_match_ids"] == ["x"]
