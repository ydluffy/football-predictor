from __future__ import annotations

from pathlib import Path

import pandas as pd

from football_predictor.data.io import read_matches_csv
from football_predictor.features.baseline import build_baseline_features, extract_labels


def test_build_baseline_features_shapes() -> None:
    df = read_matches_csv(Path(__file__).resolve().parents[1] / "data" / "sample_matches.csv")
    x = build_baseline_features(df)
    y = extract_labels(df)
    assert x.shape[0] == df.shape[0]
    assert y.shape[0] == df.shape[0]
    assert set(["odds_p_home", "odds_p_draw", "odds_p_away", "xg_diff", "xg_sum", "injury_flag", "line_move"]).issubset(
        set(x.columns)
    )
    assert pd.isna(x).sum().sum() == 0
