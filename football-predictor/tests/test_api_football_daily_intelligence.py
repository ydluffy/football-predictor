from __future__ import annotations

import pandas as pd

from data.api_football_daily_intelligence import collect_api_football_daily_intelligence
from data.api_football_prematch import append_validated_prematch_intelligence


def _fixture(fid: int, date: str, home: str = "Manchester City", away: str = "Arsenal") -> dict:
    return {"fixture": {"id": fid, "date": date, "status": {"short": "NS"}},
            "league": {"id": 39, "name": "Premier League", "season": 2026},
            "teams": {"home": {"name": home}, "away": {"name": away}}}


class FakeClient:
    def __init__(self): self.last_headers = {"x-ratelimit-requests-remaining": "90"}
    def get(self, endpoint, params):
        if endpoint == "injuries":
            return {"errors": [], "response": [{"fixture": {"id": 100}, "team": {"name": "Manchester City"},
                    "player": {"id": 9, "name": "Player X", "type": "Knee Injury", "reason": "knee"}}]}
        if endpoint == "fixtures/lineups":
            return {"errors": [], "response": [{"team": {"name": "Manchester City"},
                    "startXI": [{"player": {"id": i, "name": f"P{i}"}} for i in range(11)]}]}
        day = params["date"]
        if day == "2026-08-16": return {"errors": [], "results": 1, "response": [_fixture(100, "2026-08-16T23:00:00+08:00")]}
        if day == "2026-08-12": return {"errors": [], "results": 1, "response": [_fixture(50, "2026-08-12T20:00:00+08:00", away="Chelsea")]}
        return {"errors": [], "results": 0, "response": []}


class CrossDayFakeClient(FakeClient):
    def get(self, endpoint, params):
        if endpoint == "fixtures" and params.get("date") == "2026-08-17":
            return {"errors": [], "results": 1, "response": [_fixture(101, "2026-08-17T01:00:00+08:00")]}
        if endpoint == "injuries":
            return {"errors": [], "response": []}
        return super().get(endpoint, params)


def test_daily_collector_builds_absence_lineup_and_complete_schedule_load(tmp_path):
    scan = pd.DataFrame([{"match_id": "2026-08-16|001", "competition_id": "ENG_PREMIER_LEAGUE",
                          "kickoff": "2026-08-16T23:00:00+08:00", "home_team": "曼城", "away_team": "阿森纳"}])
    rows, mapping, audit = collect_api_football_daily_intelligence(
        client=FakeClient(), scan_fixtures=scan, date="2026-08-16",
        observed_at="2026-08-16T12:00:00Z", raw_root=tmp_path / "raw",
        include_lineups=True, include_schedule_load=True, request_interval_seconds=0,
    )
    assert len(mapping) == 1
    assert audit["schedule_calendar_complete"] is True
    assert audit["schedule_load_rows"] == 2
    assert (rows["signal_type"] == "absence").sum() == 1
    assert (rows["signal_type"] == "confirmed_starter").sum() == 11
    home_load = rows[(rows["signal_type"] == "cross_comp_matches_7d") & rows["team"].eq("曼城")]
    assert home_load.iloc[0]["numeric_value"] == 1.0
    write = append_validated_prematch_intelligence(
        rows, manual_path=tmp_path / "manual.csv", validated_path=tmp_path / "validated.csv")
    assert write["validated_rows"] == 14


def test_incomplete_schedule_calendar_never_writes_zero_loads(tmp_path):
    class FailingCalendar(FakeClient):
        def get(self, endpoint, params):
            if endpoint == "fixtures" and params.get("date") == "2026-08-13":
                raise RuntimeError("calendar unavailable")
            return super().get(endpoint, params)
    scan = pd.DataFrame([{"match_id": "2026-08-16|001", "competition_id": "ENG_PREMIER_LEAGUE",
                          "kickoff": "2026-08-16T23:00:00+08:00", "home_team": "曼城", "away_team": "阿森纳"}])
    rows, _, audit = collect_api_football_daily_intelligence(
        client=FailingCalendar(), scan_fixtures=scan, date="2026-08-16",
        observed_at="2026-08-16T12:00:00Z", raw_root=tmp_path / "raw",
        include_schedule_load=True, request_interval_seconds=0,
    )
    assert audit["schedule_calendar_complete"] is False
    assert audit["schedule_load_rows"] == 0
    assert not (rows["signal_type"] == "cross_comp_matches_7d").any()


def test_daily_collector_queries_actual_cross_day_kickoff_date(tmp_path):
    scan = pd.DataFrame([{"match_id": "2026-08-16|001", "competition_id": "ENG_PREMIER_LEAGUE",
                          "kickoff": "2026-08-17T01:00:00+08:00", "home_team": "曼城", "away_team": "阿森纳"}])
    _, mapping, audit = collect_api_football_daily_intelligence(
        client=CrossDayFakeClient(), scan_fixtures=scan, date="2026-08-16",
        observed_at="2026-08-16T12:00:00Z", raw_root=tmp_path / "raw",
        request_interval_seconds=0,
    )
    assert len(mapping) == 1
    assert audit["fixture_dates"] == ["2026-08-17"]
