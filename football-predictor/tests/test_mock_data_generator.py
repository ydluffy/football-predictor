from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.mock_data_generator import generate_mock_matches


def test_generate_mock_matches_v1_columns_and_basic_sanity():
    df = generate_mock_matches(n_rows=80, feature_version="v1")
    assert len(df) == 80
    assert {
        "match_id",
        "date",
        "league",
        "home_team",
        "away_team",
        "odds_home",
        "odds_draw",
        "odds_away",
        "actual_result",
    } <= set(df.columns)
    assert (df[["odds_home", "odds_draw", "odds_away"]].to_numpy(dtype=float) > 1.0).all()
    assert set(df["actual_result"].astype(str).unique()) <= {"H", "D", "A"}
    assert df["actual_result"].nunique() >= 2


def test_generate_mock_matches_v2_has_context_fields():
    df = generate_mock_matches(n_rows=60, feature_version="v2")
    assert {"xg_home", "xg_away", "injury_flag", "line_move"} <= set(df.columns)
    assert (pd.to_numeric(df["injury_flag"], errors="coerce").dropna().isin([0, 1])).all()
    assert df["line_move"].abs().max() <= 0.5


def test_generate_mock_matches_v3_has_sequence_and_momentum_fields():
    df = generate_mock_matches(n_rows=60, feature_version="v3")
    assert {"odds_home_open", "odds_home_last", "home_xg_last_1", "away_xga_last_3"} <= set(df.columns)
    delta = (df["odds_home_last"].astype(float) - df["odds_home_open"].astype(float)).to_numpy()
    assert np.any(np.abs(delta) > 1e-6)
    assert df[["home_xg_last_1", "home_xg_last_2", "home_xg_last_3"]].to_numpy().sum() > 0.0


def test_generate_mock_matches_invalid_feature_version_raises():
    with pytest.raises(ValueError):
        generate_mock_matches(n_rows=10, feature_version="bad")

