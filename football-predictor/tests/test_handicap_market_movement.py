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


def _movement_pair(home_team: str, away_team: str) -> pd.DataFrame:
    rows = [
        _row("open", "2026-08-16T10:00:00Z", -0.75, 1.90, 1.90, "a"),
        _row("final", "2026-08-16T18:00:00Z", -1.0, 2.00, 1.80, "a"),
    ]
    return pd.DataFrame(
        [
            {**row, "match_id": "2026-08-16|018", "home_team": home_team, "away_team": away_team}
            for row in rows
        ]
    )


def test_english_team_names_are_localized_to_the_fixtures_feed_names():
    row = build_api_football_handicap_movement(_movement_pair("Racing Santander", "Villarreal")).iloc[0]

    assert row["home_team"] == "桑坦德"
    assert row["away_team"] == "比利亚雷"


def test_team_names_that_already_contain_chinese_are_kept_verbatim():
    row = build_api_football_handicap_movement(_movement_pair("桑坦德竞技", "比利亚雷亚尔")).iloc[0]

    assert row["home_team"] == "桑坦德竞技"
    assert row["away_team"] == "比利亚雷亚尔"
