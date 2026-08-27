from __future__ import annotations

import pandas as pd

from data.prematch_coverage import audit_prematch_coverage


def test_coverage_audit_distinguishes_timestamped_snapshot_rows() -> None:
    historical = pd.DataFrame(
        {
            "match_id": ["m1"],
            "home_shots": [10],
            "away_shots": [8],
            "odds_home": [2.0],
        }
    )
    snapshots = pd.DataFrame(
        {
            "event_id": ["e1", "e2"],
            "captured_at": ["2026-08-10T10:00:00Z", "2026-08-10T15:00:00Z"],
            "commence_time": ["2026-08-10T14:00:00Z", "2026-08-10T14:00:00Z"],
        }
    )
    intelligence = pd.DataFrame(columns=["observed_at"])
    sporttery = pd.DataFrame(
        [{"snapshot_id": "s1", "fixture_count": 2, "fixtures_before_kickoff_count": 1}]
    )
    audit = audit_prematch_coverage(
        historical,
        market_snapshot_history=snapshots,
        sporttery_snapshot_index=sporttery,
        prematch_intelligence=intelligence,
    )
    assert audit["field_groups"]["confirmed_lineups"]["available"] is False
    assert audit["historical_match_stats"]["available"] is True
    assert audit["market_snapshot_history"]["kickoff_safe_rows"] == 1
    assert audit["market_snapshot_history"]["post_kickoff_or_invalid_rows"] == 1
    assert audit["generic_prematch_dataset"]["exists"] is True
    assert audit["generic_prematch_dataset"]["rows"] == 0
    assert audit["generic_prematch_dataset"]["groups"]["absences"]["rows"] == 0
    assert audit["sporttery_snapshot_archive"]["safe_fixture_observations"] == 1


def test_coverage_audit_reports_generic_signal_rows_separately_from_historical_columns() -> None:
    intelligence = pd.DataFrame([
        {"match_id":"m1","signal_type":"absence","observed_at":"2026-08-16T10:00:00Z"},
        {"match_id":"m1","signal_type":"confirmed_starter","observed_at":"2026-08-16T11:00:00Z"},
        {"match_id":"m2","signal_type":"cross_comp_matches_7d","observed_at":"2026-08-16T09:00:00Z"},
    ])
    audit = audit_prematch_coverage(pd.DataFrame({"match_id":["h1"]}), prematch_intelligence=intelligence)
    groups = audit["generic_prematch_dataset"]["groups"]
    assert groups["absences"] == {"available": True, "rows": 1, "matches": 1}
    assert groups["confirmed_lineups"]["rows"] == 1
    assert groups["cross_comp_schedule"]["matches"] == 1
    assert "absences" not in audit["generic_missing_priorities"]
