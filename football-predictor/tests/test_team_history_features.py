from __future__ import annotations

import pandas as pd

from features.team_history_features import build_team_history_features


def test_team_history_features_do_not_leak_same_matchday_results():
    df = pd.DataFrame(
        {
            "date": ["2025-01-01", "2025-01-01", "2025-01-02"],
            "home_team": ["A", "A", "A"],
            "away_team": ["B", "C", "D"],
            "home_goals": [2, 3, 1],
            "away_goals": [0, 0, 1],
            "actual_result": ["H", "H", "D"],
        }
    )

    out = build_team_history_features(df)

    assert out.loc[0, "home_matches_seen"] == 0.0
    assert out.loc[1, "home_matches_seen"] == 0.0
    assert out.loc[0, "home_form_points_5"] == 0.0
    assert out.loc[1, "home_form_points_5"] == 0.0
    assert out.loc[2, "home_matches_seen"] == 2.0
    assert out.loc[2, "home_form_points_5"] == 3.0
    assert out.loc[2, "elo_home"] > 1500.0 / 400.0


def test_team_history_features_use_only_prior_matches():
    df = pd.DataFrame(
        {
            "date": ["2025-01-01", "2025-01-02"],
            "home_team": ["A", "B"],
            "away_team": ["B", "A"],
            "home_goals": [2, 0],
            "away_goals": [0, 1],
            "actual_result": ["H", "A"],
        }
    )

    out = build_team_history_features(df)

    assert out.loc[1, "away_matches_seen"] == 1.0
    assert out.loc[1, "away_form_points_5"] == 3.0
    assert out.loc[1, "away_goals_for_5"] == 2.0
    assert out.loc[1, "away_goals_against_5"] == 0.0


def test_team_history_features_inference_without_history_defaults_to_zero():
    df = pd.DataFrame(
        {
            "date": ["2025-01-03"],
            "home_team": ["A"],
            "away_team": ["B"],
        }
    )

    out = build_team_history_features(df)

    assert (out.to_numpy() == 0.0).all()


def test_match_stats_history_does_not_leak_same_matchday():
    df = pd.DataFrame(
        {
            "date": ["2025-01-01", "2025-01-01", "2025-01-02"],
            "home_team": ["A", "A", "A"],
            "away_team": ["B", "C", "D"],
            "home_goals": [1, 1, 0],
            "away_goals": [0, 0, 0],
            "home_shots": [12, 20, 8],
            "away_shots": [5, 4, 7],
            "home_shots_on_target": [5, 9, 2],
            "away_shots_on_target": [2, 1, 2],
            "home_corners": [6, 8, 3],
            "away_corners": [2, 1, 4],
            "home_yellow_cards": [1, 2, 1],
            "away_yellow_cards": [2, 1, 1],
            "home_red_cards": [0, 0, 0],
            "away_red_cards": [0, 0, 0],
            "actual_result": ["H", "H", "D"],
        }
    )

    out = build_team_history_features(df)

    assert out.loc[0, "home_match_stats_seen_5"] == 0.0
    assert out.loc[1, "home_match_stats_seen_5"] == 0.0
    assert out.loc[2, "home_match_stats_seen_5"] == 2.0
    assert out.loc[2, "shots_on_target_diff_5"] == 7.0
    assert out.loc[2, "net_shots_on_target_diff_5"] == 5.5
