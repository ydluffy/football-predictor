from __future__ import annotations

import pandas as pd

from world_cup.data_source_audit import audit_prediction_coverage
from world_cup.data_source_audit import audit_source_frame
from world_cup.data_source_audit import registry_as_rows


def test_registry_exposes_core_world_cup_sources():
    rows = registry_as_rows()
    source_ids = {row["source_id"] for row in rows}

    assert "espn_world_cup_live" in source_ids
    assert "sporttery_lottery_gov" in source_ids
    assert "leisu_public" in source_ids
    assert any(row["browser_required"] for row in rows if row["source_id"] == "sporttery_lottery_gov")


def test_audit_source_frame_reports_missing_required_fields():
    frame = pd.DataFrame(
        [
            {
                "date": "2026-06-26",
                "home_team": "Ecuador",
                "away_team": "Germany",
            }
        ]
    )

    audit = audit_source_frame("sporttery_lottery_gov", frame)

    assert audit["status"] == "schema_error"
    assert "match_number" in audit["issues"][0]


def test_audit_source_frame_reports_ok_with_required_market_fields():
    frame = pd.DataFrame(
        [
            {
                "date": "2026-06-26",
                "match_number": "055",
                "home_team": "Ecuador",
                "away_team": "Germany",
                "home_handicap": "+1",
                "rqspf_odds_home": 2.65,
                "rqspf_odds_draw": 3.72,
                "rqspf_odds_away": 2.07,
            }
        ]
    )

    audit = audit_source_frame("sporttery_lottery_gov", frame)

    assert audit["status"] == "ok"
    assert audit["rows"] == 1
    assert not audit["issues"]


def test_audit_prediction_coverage_does_not_count_zero_absence_rows_as_data():
    predictions = pd.DataFrame(
        [
            {
                "base_p_home": 0.4,
                "base_p_draw": 0.3,
                "base_p_away": 0.3,
                "sporttery_market_source": "lottery.gov.cn:zqspf",
                "handicap_market_home_probability": 0.4,
                "line_movement_snapshots": 0,
                "home_absence_count": 0,
                "away_absence_count": 0,
                "home_realtime_lineup_confirmed": 0,
                "away_realtime_lineup_confirmed": 0,
            }
        ]
    )

    audit = audit_prediction_coverage(predictions)

    assert audit["dimension_coverage"]["historical_team_model"]["coverage"] == 1.0
    assert audit["dimension_coverage"]["sporttery_handicap"]["coverage"] == 1.0
    assert audit["dimension_coverage"]["absences_suspensions"]["coverage"] == 0.0
    assert audit["status"] == "insufficient"
