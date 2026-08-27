from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from import_api_football_odds_snapshot import build_mapping_from_scan


class FakeClient:
    def get(self, path, params):
        assert path == "fixtures"
        requested_date = params["date"]
        return {
            "results": 2, "errors": [], "response": [
                {"fixture": {"id": 1, "date": "2026-08-16T20:00:00+08:00"},
                 "league": {"id": 39, "name": "Premier League", "season": 2026},
                 "teams": {"home": {"name": "Manchester City"}, "away": {"name": "Arsenal"}}},
                {"fixture": {"id": 2, "date": "2026-08-16T23:00:00+08:00"},
                 "league": {"id": 140, "name": "La Liga", "season": 2026},
                 "teams": {"home": {"name": "Racing de Santander"}, "away": {"name": "Villarreal CF"}}},
            ] if requested_date == "2026-08-16" else [],
        }


class CrossDayFakeClient:
    def get(self, path, params):
        assert path == "fixtures"
        assert params["date"] == "2026-08-17"
        return {"results": 1, "errors": [], "response": [
            {"fixture": {"id": 3, "date": "2026-08-17T01:00:00+08:00"},
             "league": {"id": 39, "name": "Premier League", "season": 2026},
             "teams": {"home": {"name": "Manchester City"}, "away": {"name": "Arsenal"}}},
        ]}


def _scan(path: Path) -> None:
    path.write_text(json.dumps({"fixtures": [
        {"match_id": "2026-08-16|001", "competition_id": "ENG_PREMIER_LEAGUE",
         "kickoff": "2026-08-16T20:00:00+08:00", "home_team": "曼城", "away_team": "阿森纳"},
        {"match_id": "2026-08-16|018", "competition_id": "ESP_LA_LIGA",
         "kickoff": "2026-08-16T23:00:00+08:00", "home_team": "桑坦德", "away_team": "比利亚雷"},
    ]}, ensure_ascii=False), encoding="utf-8")


def test_scan_without_league_filter_maps_all_unique_fixtures(tmp_path):
    path = tmp_path / "scan.json"; _scan(path)
    mapping, audit = build_mapping_from_scan(client=FakeClient(), scan_path=path, league_id=0, date="2026-08-16")
    assert len(mapping) == 2
    assert audit["league_filter"] is None


def test_optional_league_filter_still_limits_mapping(tmp_path):
    path = tmp_path / "scan.json"; _scan(path)
    mapping, audit = build_mapping_from_scan(client=FakeClient(), scan_path=path, league_id=140, date="2026-08-16")
    assert mapping["source_fixture_id"].tolist() == ["2"]
    assert audit["league_filter"] == 140


def test_scan_queries_actual_cross_day_kickoff_date(tmp_path):
    path = tmp_path / "scan.json"
    path.write_text(json.dumps({"fixtures": [
        {"match_id": "2026-08-16|001", "competition_id": "ENG_PREMIER_LEAGUE",
         "kickoff": "2026-08-17T01:00:00+08:00", "home_team": "曼城", "away_team": "阿森纳"},
    ]}, ensure_ascii=False), encoding="utf-8")
    mapping, audit = build_mapping_from_scan(
        client=CrossDayFakeClient(), scan_path=path, league_id=0, date="2026-08-16"
    )
    assert mapping["source_fixture_id"].tolist() == ["3"]
    assert audit["fixture_dates"] == ["2026-08-17"]
