from __future__ import annotations

import pandas as pd
import pytest

from evaluate.asian_handicap_research import (
    audit_live_market_archives,
    build_exact_handicap_dataset,
    exact_line_label,
    settle_asian_handicap,
    split_asian_line,
    summarize_exact_handicaps,
)


def test_exact_labels_and_quarter_split():
    assert exact_line_label(-0.25) == "平半"
    assert exact_line_label(-0.5) == "半球"
    assert exact_line_label(-1.0) == "一球"
    assert exact_line_label(-1.5) == "球半"
    assert exact_line_label(-2.0) == "两球"
    assert split_asian_line(-0.25) == (-0.5, 0.0)
    assert split_asian_line(-0.75) == (-1.0, -0.5)


@pytest.mark.parametrize(
    ("score", "line", "expected_result", "expected_return"),
    [
        ((1, 0), -0.75, "half_win", 0.45),
        ((1, 0), -1.0, "push", 0.0),
        ((1, 0), -1.25, "half_loss", -0.5),
        ((2, 0), -1.5, "full_win", 0.9),
        ((0, 0), -0.25, "half_loss", -0.5),
    ],
)
def test_home_quarter_line_settlement(score, line, expected_result, expected_return):
    settled = settle_asian_handicap(*score, line, side="home", decimal_odds=1.9)
    assert settled.result == expected_result
    assert settled.net_return == pytest.approx(expected_return)


def test_away_side_inverts_home_line():
    settled = settle_asian_handicap(0, 0, -0.25, side="away", decimal_odds=2.0)
    assert settled.result == "half_win"
    assert settled.net_return == pytest.approx(0.5)


def test_build_dataset_and_summary_preserve_exact_lines():
    source = pd.DataFrame(
        [
            {
                "match_id": "m1", "date": "2025-01-01", "season": "2024-25", "league": "E0",
                "home_team": "A", "away_team": "B", "home_goals": 1, "away_goals": 0,
                "AHh": -0.75, "AvgAHH": 1.9, "AvgAHA": 2.0,
                "AHCh": -1.0, "AvgCAHH": 2.0, "AvgCAHA": 1.9,
            },
            {
                "match_id": "m2", "date": "2025-01-02", "season": "2024-25", "league": "E0",
                "home_team": "C", "away_team": "D", "home_goals": 0, "away_goals": 0,
                "AHh": 0.25, "AvgAHH": 2.0, "AvgAHA": 1.9,
                "AHCh": 0.25, "AvgCAHH": 2.0, "AvgCAHA": 1.9,
            },
        ]
    )
    dataset, audit = build_exact_handicap_dataset(source)
    assert audit["research_rows"] == 2
    assert dataset.loc[0, "opening_favorite_result"] == "half_win"
    assert dataset.loc[0, "home_line_movement_quarters"] == -1
    assert dataset.loc[1, "opening_favorite_side"] == "away"
    summary = summarize_exact_handicaps(
        dataset, group_columns=["opening_line_depth", "opening_line_label"], minimum_observation=2
    )
    assert set(summary["opening_line_label"]) == {"平半", "半一"}
    assert set(summary["status"]) == {"observation_only"}


def test_live_archive_audit_keeps_inner_and_outer_separate():
    sporttery = pd.DataFrame(
        [
            {"date": "2026-08-10", "match_number": "001", "captured_at": "10:00", "home_handicap": -1},
            {"date": "2026-08-10", "match_number": "001", "captured_at": "11:00", "home_handicap": -1},
        ]
    )
    external = pd.DataFrame(
        [
            {"event_id": "e1", "captured_at": "10:00", "external_home_spread_point": -0.75},
            {"event_id": "e1", "captured_at": "11:00", "external_home_spread_point": -1.0},
        ]
    )
    audit = audit_live_market_archives(sporttery, external)
    assert audit["sporttery_unique_fixtures"] == 1
    assert audit["external_unique_events"] == 1
    assert audit["time_aligned_pair_count"] is None
