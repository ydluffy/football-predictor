from __future__ import annotations

import pandas as pd

from features.schedule_features import build_schedule_features


def test_schedule_features_use_only_prior_dates():
    df = pd.DataFrame(
        {
            "date": ["2025-01-01", "2025-01-04", "2025-01-08"],
            "home_team": ["A", "C", "A"],
            "away_team": ["B", "A", "D"],
        }
    )

    out = build_schedule_features(df)

    assert out.loc[0, "home_schedule_seen"] == 0.0
    assert out.loc[1, "away_rest_days"] == 3.0
    assert out.loc[1, "away_short_rest_flag"] == 1.0
    assert out.loc[2, "home_rest_days"] == 4.0
    assert out.loc[2, "home_matches_7d"] == 2.0
    assert out.loc[2, "home_matches_14d"] == 2.0


def test_schedule_features_do_not_leak_same_matchday():
    df = pd.DataFrame(
        {
            "date": ["2025-01-01", "2025-01-01", "2025-01-03"],
            "home_team": ["A", "A", "A"],
            "away_team": ["B", "C", "D"],
        }
    )

    out = build_schedule_features(df)

    assert out.loc[0, "home_schedule_seen"] == 0.0
    assert out.loc[1, "home_schedule_seen"] == 0.0
    assert out.loc[2, "home_matches_7d"] == 2.0
    assert out.loc[2, "home_rest_days"] == 2.0


def test_schedule_features_include_prior_external_matches():
    league = pd.DataFrame(
        {
            "date": ["2025-01-01", "2025-01-08"],
            "home_team": ["A", "A"],
            "away_team": ["B", "C"],
        }
    )
    external = pd.DataFrame(
        {
            "date": ["2025-01-05"],
            "home_team": ["A"],
            "away_team": [None],
        }
    )

    out = build_schedule_features(league, external_calendar=external)

    assert out.loc[1, "home_rest_days"] == 3.0
    assert out.loc[1, "home_matches_7d"] == 2.0
    assert out.loc[1, "home_short_rest_flag"] == 1.0
