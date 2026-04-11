from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from features.momentum_features import build_momentum_features, exp_decay_mean


def test_exp_decay_mean_weights_recent_highest():
    v = exp_decay_mean([10.0, 0.0, 0.0], decay=0.85)
    assert v > 3.5


def test_exp_decay_mean_invalid_decay_raises():
    with pytest.raises(ValueError):
        exp_decay_mean([1.0], decay=1.0)


def test_build_momentum_features_missing_fields_all_zero():
    df = pd.DataFrame({"any": [1, 2, 3]})
    out = build_momentum_features(df, decay=0.85)
    assert (out.to_numpy() == 0.0).all()


def test_build_momentum_features_nan_safe_and_columns():
    df = pd.DataFrame(
        {
            "home_xg_last_1": [1.2, np.nan],
            "home_xg_last_2": [1.0, 0.8],
            "home_xg_last_3": [0.7, 0.6],
            "away_xg_last_1": [0.9, 1.1],
            "away_xg_last_2": [0.8, np.nan],
            "away_xg_last_3": [0.5, 0.4],
            "home_xga_last_1": [0.6, 0.7],
            "home_xga_last_2": [0.5, 0.6],
            "home_xga_last_3": [0.4, 0.5],
            "away_xga_last_1": [0.7, 0.8],
            "away_xga_last_2": [0.6, 0.7],
            "away_xga_last_3": [0.5, 0.6],
        }
    )
    out = build_momentum_features(df, decay=0.85)
    expected = {
        "home_attack_momentum",
        "away_attack_momentum",
        "home_defense_momentum",
        "away_defense_momentum",
        "attack_momentum_diff",
        "defense_momentum_diff",
    }
    assert expected <= set(out.columns)
    assert not np.isnan(out.to_numpy()).any()
