from __future__ import annotations

import numpy as np
import pandas as pd

from features.odds_sequence_features import build_odds_sequence_features


def test_build_odds_sequence_features_full_fields():
    df = pd.DataFrame(
        {
            "odds_home_open": [2.0, 2.0],
            "odds_home_last": [1.8, 2.2],
            "odds_draw_open": [3.0, 3.0],
            "odds_draw_last": [3.3, 2.7],
            "odds_away_open": [4.0, 4.0],
            "odds_away_last": [4.4, 3.6],
            "odds_home_t1": [1.85, 2.1],
            "odds_home_t2": [1.8, 2.2],
            "odds_draw_t1": [3.2, 2.8],
            "odds_draw_t2": [3.3, 2.7],
            "odds_away_t1": [4.2, 3.7],
            "odds_away_t2": [4.4, 3.6],
        }
    )
    X = build_odds_sequence_features(df)
    expected = {
        "delta_home_open_last",
        "delta_draw_open_last",
        "delta_away_open_last",
        "pct_home_open_last",
        "pct_draw_open_last",
        "pct_away_open_last",
        "home_odds_drop_flag",
        "draw_odds_drop_flag",
        "away_odds_drop_flag",
        "odds_move_abs_sum",
        "odds_move_max_abs",
        "recent_home_move",
        "recent_draw_move",
        "recent_away_move",
    }
    assert expected <= set(X.columns)

    assert np.isclose(X.loc[0, "delta_home_open_last"], -0.2)
    assert np.isclose(X.loc[1, "delta_home_open_last"], 0.2)
    assert int(X.loc[0, "home_odds_drop_flag"]) == 1
    assert int(X.loc[1, "home_odds_drop_flag"]) == 0
    assert np.isclose(X.loc[0, "recent_home_move"], -0.05)


def test_build_odds_sequence_features_missing_fields_all_zero():
    df = pd.DataFrame({"any": [1, 2, 3]})
    X = build_odds_sequence_features(df)
    assert (X.to_numpy() == 0.0).all()


def test_build_odds_sequence_features_nan_safe_degrade_to_zero():
    df = pd.DataFrame(
        {
            "odds_home_open": [2.0, np.nan],
            "odds_home_last": [np.nan, 2.2],
            "odds_draw_open": [3.0, 3.0],
            "odds_draw_last": [np.nan, np.nan],
            "odds_away_open": [4.0, 4.0],
            "odds_away_last": [4.4, np.nan],
            "odds_home_t1": [np.nan, 2.1],
            "odds_home_t2": [1.8, np.nan],
        }
    )
    X = build_odds_sequence_features(df)
    assert float(X.loc[0, "delta_home_open_last"]) == 0.0
    assert float(X.loc[1, "delta_home_open_last"]) == 0.0
    assert float(X.loc[1, "delta_draw_open_last"]) == 0.0
    assert float(X.loc[1, "recent_home_move"]) == 0.0
    assert not np.isnan(X.to_numpy()).any()

