from __future__ import annotations

import pandas as pd

from features.basic_features import build_basic_features
from features.season_context_features import build_season_context_features


def _league_rows(count: int = 31) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-08-01", periods=count, freq="7D").astype(str),
            "season": ["2025-26"] * count,
            "league": ["E0"] * count,
            "home_team": ["Arsenal"] * count,
            "away_team": ["Chelsea"] * count,
            "odds_home": [2.0] * count,
            "odds_draw": [3.3] * count,
            "odds_away": [3.8] * count,
            "actual_result": ["H"] * count,
        }
    )


def test_season_context_uses_only_matches_before_kickoff() -> None:
    features = build_season_context_features(_league_rows())

    assert features.loc[0, "home_matches_played_before"] == 0.0
    assert features.loc[1, "home_matches_played_before"] == 1.0
    assert features.loc[0, "season_early_flag"] == 1.0
    assert features.loc[29, "season_late_flag"] == 1.0
    assert features.loc[29, "season_progress"] == 29.0 / 38.0


def test_same_day_rows_cannot_leak_into_one_another() -> None:
    frame = _league_rows(2)
    frame["date"] = ["2025-08-01", "2025-08-01"]

    features = build_season_context_features(frame)

    assert features["home_matches_played_before"].tolist() == [0.0, 0.0]


def test_calendar_year_competition_resets_by_year() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2025-03-01", "2025-03-08", "2026-03-01"],
            "league": ["日职联"] * 3,
            "home_team": ["横滨水手"] * 3,
            "away_team": ["鹿岛鹿角"] * 3,
        }
    )

    features = build_season_context_features(frame)

    assert features["home_matches_played_before"].tolist() == [0.0, 1.0, 0.0]


def test_v7_exposes_schedule_and_season_context_as_experimental_features() -> None:
    frame = _league_rows(4)

    features, target, names = build_basic_features(frame, feature_version="v7")

    assert len(features) == len(target) == 4
    assert "home_rest_days" in names
    assert "season_progress" in names
    assert "competition_known_flag" in names
