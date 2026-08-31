from __future__ import annotations

import pandas as pd

from features.handicap_market_movement import build_api_football_handicap_movement


def _row(snapshot: str, captured: str, line: float, home_odds: float, away_odds: float, bookmaker: str):
    return {
        "match_id": "2026-08-17|001",
        "snapshot_id": snapshot,
        "captured_at": captured,
        "source_fixture_id": "fixture-1",
        "competition_id": "ENG_PREMIER_LEAGUE",
        "home_team": "Manchester City",
        "away_team": "Arsenal",
        "kickoff_at": "2026-08-17T20:00:00Z",
        "bookmaker_id": bookmaker,
        "home_handicap": line,
        "home_odds": home_odds,
        "away_odds": away_odds,
        "mapping_status": "mapped",
        "before_kickoff": True,
        "eligible_for_primary_research": True,
    }


def test_market_movement_uses_bookmaker_medians_and_correct_home_line_direction():
    history = pd.DataFrame(
        [
            _row("open", "2026-08-17T10:00:00Z", -0.75, 1.90, 1.90, "a"),
            _row("open", "2026-08-17T10:00:00Z", -0.50, 1.80, 2.00, "b"),
            _row("final", "2026-08-17T18:00:00Z", -1.00, 2.05, 1.75, "a"),
            _row("final", "2026-08-17T18:00:00Z", -1.00, 2.00, 1.80, "b"),
        ]
    )

    result = build_api_football_handicap_movement(history)
    row = result.iloc[0]

    assert row["opening_home_handicap_median"] == -0.625
    assert row["latest_home_handicap_median"] == -1.0
    assert row["home_line_strength_delta"] == 0.375
    assert row["snapshot_count"] == 2
    assert row["bookmaker_count"] == 2
    assert bool(row["safe_for_shadow_features"]) is True
    assert bool(row["line_upgrade_without_price_support"]) is True


def test_post_kickoff_and_unmapped_rows_are_excluded():
    history = pd.DataFrame(
        [
            _row("late", "2026-08-17T21:00:00Z", -1.0, 1.9, 1.9, "a"),
            {**_row("open", "2026-08-17T10:00:00Z", -0.75, 1.9, 1.9, "b"), "mapping_status": "unmapped"},
        ]
    )

    result = build_api_football_handicap_movement(history)

    assert result.empty
