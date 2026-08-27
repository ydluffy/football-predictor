from __future__ import annotations

import pandas as pd

from data.api_football_prematch import append_validated_prematch_intelligence
from data.schedule_load_intelligence import build_schedule_load_intelligence


def test_schedule_load_uses_only_prior_finished_matches_and_validates(tmp_path):
    scan = pd.DataFrame([{"match_id":"2026-08-16|018","competition_id":"ESP_LA_LIGA",
        "kickoff":"2026-08-16T23:00:00+08:00","home_team":"桑坦德","away_team":"比利亚雷"}])
    external = pd.DataFrame([
        {"source_fixture_id":"current","kickoff_time":"2026-08-16T15:00:00Z","home_team":"Racing de Santander","away_team":"Villarreal CF","status":"TIMED"},
        {"source_fixture_id":"prior1","kickoff_time":"2026-08-12T15:00:00Z","home_team":"Villarreal CF","away_team":"Getafe CF","status":"FINISHED"},
        {"source_fixture_id":"postponed","kickoff_time":"2026-08-11T15:00:00Z","home_team":"Racing de Santander","away_team":"Elche CF","status":"POSTPONED"},
    ])
    rows, mapping, audit = build_schedule_load_intelligence(
        scan_fixtures=scan, external_matches=external, observed_at="2026-08-16T12:00:00Z",
        source="football_data_org", source_url="https://example.test/matches")
    assert len(mapping) == 1
    assert audit["schedule_load_rows"] == 2
    assert rows.loc[rows.team.eq("比利亚雷"), "numeric_value"].iloc[0] == 1.0
    assert rows.loc[rows.team.eq("桑坦德"), "numeric_value"].iloc[0] == 0.0
    write = append_validated_prematch_intelligence(rows, manual_path=tmp_path/"m.csv", validated_path=tmp_path/"v.csv")
    assert write["validated_rows"] == 2
