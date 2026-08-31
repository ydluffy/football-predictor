from __future__ import annotations

import numpy as np
import pandas as pd

from features.kelly_features import build_kelly_proxy_features


def test_build_kelly_proxy_features_normal_case_and_column_stability():
    df = pd.DataFrame(
        {
            "odds_home_open": [2.0, 2.0],
            "odds_draw_open": [3.0, 3.0],
            "odds_away_open": [4.0, 4.0],
            "odds_home_last": [1.8, 2.2],
            "odds_draw_last": [3.2, 2.8],
            "odds_away_last": [4.2, 3.8],
        }
    )
    out = build_kelly_proxy_features(df)
    expected_cols = [
        "kelly_proxy_home",
        "kelly_proxy_draw",
        "kelly_proxy_away",
        "delta_kelly_proxy_home",
        "delta_kelly_proxy_draw",
        "delta_kelly_proxy_away",
        "kelly_direction_home",
        "kelly_direction_draw",
        "kelly_direction_away",
        "kelly_proxy_spread",
        "kelly_proxy_max_shift",
    ]
    assert list(out.columns) == expected_cols
    assert not np.isnan(out.to_numpy()).any()

    assert set(out["kelly_direction_home"].astype(int).unique()) <= {-1, 0, 1}
    assert out.loc[0, "kelly_proxy_max_shift"] >= 0.0


def test_build_kelly_proxy_features_missing_fields_all_zero():
    df = pd.DataFrame({"any": [1, 2]})
    out = build_kelly_proxy_features(df)
    assert (out.to_numpy() == 0.0).all()


def test_build_kelly_proxy_features_uses_base_with_last_odds():
    df = pd.DataFrame(
        {
            "odds_home": [2.0],
            "odds_draw": [3.2],
            "odds_away": [4.0],
            "odds_home_last": [1.8],
            "odds_draw_last": [3.4],
            "odds_away_last": [4.5],
        }
    )
    out = build_kelly_proxy_features(df)

    assert out.loc[0, "delta_kelly_proxy_home"] > 0
    assert out.loc[0, "kelly_direction_home"] == 1


def test_build_kelly_proxy_features_nan_safe_degrade_to_zero():
    df = pd.DataFrame(
        {
            "odds_home_open": [2.0, np.nan],
            "odds_draw_open": [3.0, 3.0],
            "odds_away_open": [4.0, 4.0],
            "odds_home_last": [np.nan, 2.2],
            "odds_draw_last": [3.2, np.nan],
            "odds_away_last": [4.2, 3.8],
        }
    )
    out = build_kelly_proxy_features(df)
    assert float(out.loc[0, "kelly_proxy_home"]) == 0.0
    assert float(out.loc[1, "kelly_proxy_draw"]) == 0.0
    assert not np.isnan(out.to_numpy()).any()
