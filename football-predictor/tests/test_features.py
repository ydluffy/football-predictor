from __future__ import annotations

import pandas as pd

import numpy as np
import pytest

from features.basic_features import build_basic_features, build_inference_features


def test_build_basic_features_outputs_X_y_and_expected_columns():
    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3"],
            "odds_home": [1.9, 2.1, 1.8],
            "odds_draw": [3.2, 3.0, 3.4],
            "odds_away": [4.1, 3.7, 4.5],
            "actual_result": ["H", "D", "A"],
        }
    )
    X, y, feature_names = build_basic_features(df)
    assert len(X) == len(df)
    assert len(y) == len(df)
    assert set(y.unique()) <= {"H", "D", "A"}

    expected_cols = {
        "implied_home",
        "implied_draw",
        "implied_away",
        "norm_home",
        "norm_draw",
        "norm_away",
        "odds_diff_home_away",
        "draw_vs_avg",
        "xg_diff",
        "xg_sum",
        "injury_flag",
        "line_move",
    }
    assert expected_cols <= set(X.columns)
    assert len(X) == len(df)
    assert X.select_dtypes("number").shape[1] == X.shape[1]

    assert feature_names == list(X.columns)

    row_sums = X[["norm_home", "norm_draw", "norm_away"]].sum(axis=1).to_numpy()
    assert np.allclose(row_sums, 1.0)


def test_build_basic_features_missing_columns_raises():
    df = pd.DataFrame({"odds_home": [1.9]})
    with pytest.raises(ValueError):
        build_basic_features(df)


def test_build_basic_features_empty_data_raises():
    df = pd.DataFrame(columns=["odds_home", "odds_draw", "odds_away", "actual_result"])
    with pytest.raises(ValueError):
        build_basic_features(df)


def test_build_basic_features_optional_fields_are_safe_defaults():
    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "odds_home": [1.9, 2.1],
            "odds_draw": [3.2, 3.0],
            "odds_away": [4.1, 3.7],
            "actual_result": ["H", "D"],
        }
    )
    X, _, _ = build_basic_features(df)
    assert np.allclose(X["xg_diff"].to_numpy(), 0.0)
    assert np.allclose(X["xg_sum"].to_numpy(), 0.0)
    assert np.allclose(X["injury_flag"].to_numpy(), 0.0)
    assert np.allclose(X["line_move"].to_numpy(), 0.0)


def test_build_basic_features_optional_fields_nan_are_filled():
    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "odds_home": [1.9, 2.1],
            "odds_draw": [3.2, 3.0],
            "odds_away": [4.1, 3.7],
            "xg_home": [np.nan, 1.2],
            "xg_away": [0.8, np.nan],
            "injury_flag": [None, "yes"],
            "line_move": [np.nan, "0.05"],
            "actual_result": ["H", "A"],
        }
    )
    X, _, _ = build_basic_features(df)
    assert not np.isnan(X.to_numpy()).any()


def test_build_basic_features_v1_has_fewer_columns_than_v2():
    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "odds_home": [1.9, 2.1],
            "odds_draw": [3.2, 3.0],
            "odds_away": [4.1, 3.7],
            "xg_home": [1.1, 0.9],
            "xg_away": [0.8, 1.2],
            "injury_flag": [1, 0],
            "line_move": [0.05, -0.02],
            "actual_result": ["H", "A"],
        }
    )
    X1, _, _ = build_basic_features(df, feature_version="v1")
    X2, _, _ = build_basic_features(df, feature_version="v2")
    assert X1.shape[1] < X2.shape[1]
    assert "xg_diff" not in X1.columns
    assert "line_move" not in X1.columns


def test_build_basic_features_v3_has_more_columns_than_v2():
    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "odds_home": [2.0, 2.0],
            "odds_draw": [3.0, 3.0],
            "odds_away": [4.0, 4.0],
            "odds_home_open": [2.0, 2.0],
            "odds_home_last": [1.8, 2.2],
            "odds_draw_open": [3.0, 3.0],
            "odds_draw_last": [3.3, 2.7],
            "odds_away_open": [4.0, 4.0],
            "odds_away_last": [4.4, 3.6],
            "home_xg_last_1": [1.5, 0.5],
            "home_xg_last_2": [1.0, 0.4],
            "home_xg_last_3": [0.8, 0.3],
            "away_xg_last_1": [0.8, 1.2],
            "away_xg_last_2": [0.6, 1.0],
            "away_xg_last_3": [0.5, 0.9],
            "home_xga_last_1": [0.7, 0.8],
            "home_xga_last_2": [0.6, 0.7],
            "home_xga_last_3": [0.5, 0.6],
            "away_xga_last_1": [0.9, 0.7],
            "away_xga_last_2": [0.8, 0.6],
            "away_xga_last_3": [0.7, 0.5],
            "actual_result": ["H", "A"],
        }
    )
    X2, _, _ = build_basic_features(df, feature_version="v2")
    X3, _, _ = build_basic_features(df, feature_version="v3")
    assert X3.shape[1] > X2.shape[1]

    expected = {
        "delta_home_open_last",
        "odds_move_abs_sum",
        "kelly_proxy_home",
        "kelly_proxy_max_shift",
        "home_attack_momentum",
        "away_defense_momentum",
    }
    assert expected <= set(X3.columns)

    assert X3.loc[0, "delta_home_open_last"] < 0.0
    assert X3.loc[1, "delta_home_open_last"] > 0.0


def test_build_basic_features_v3_runs_when_missing_extra_fields():
    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "odds_home": [1.9, 2.1],
            "odds_draw": [3.2, 3.0],
            "odds_away": [4.1, 3.7],
            "actual_result": ["H", "D"],
        }
    )
    X, _, _ = build_basic_features(df, feature_version="v3")
    assert np.allclose(X["delta_home_open_last"].to_numpy(), 0.0)
    assert X["kelly_proxy_home"].between(0.0, 1.0).all()
    assert np.allclose(X["delta_kelly_proxy_home"].to_numpy(), 0.0)
    assert np.allclose(X["home_attack_momentum"].to_numpy(), 0.0)


def test_build_inference_features_does_not_require_actual_result():
    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "odds_home": [1.9, 2.1],
            "odds_draw": [3.2, 3.0],
            "odds_away": [4.1, 3.7],
        }
    )
    X, feature_names = build_inference_features(df, feature_version="v3")
    assert len(X) == len(df)
    assert "norm_home" in X.columns
    assert feature_names == list(X.columns)
