from __future__ import annotations

import pandas as pd
import pytest

from evaluate.splitters import time_based_split


def test_time_based_split_sorts_and_splits_by_time():
    df = pd.DataFrame(
        {
            "match_id": ["m3", "m1", "m2", "m4", "m5"],
            "date": ["2025-01-03", "2025-01-01", "2025-01-02", "2025-01-04", "2025-01-04"],
            "odds_home": [2.0, 1.8, 1.9, 2.1, 2.2],
            "odds_draw": [3.2, 3.1, 3.0, 3.3, 3.4],
            "odds_away": [3.9, 4.2, 4.1, 3.6, 3.5],
            "actual_result": ["H", "D", "A", "H", "A"],
        }
    )

    train_df, test_df = time_based_split(df, test_size=0.4)
    assert len(train_df) + len(test_df) == len(df)
    assert train_df.index.tolist() == list(range(len(train_df)))
    assert test_df.index.tolist() == list(range(len(test_df)))

    assert train_df["date"].is_monotonic_increasing
    assert test_df["date"].is_monotonic_increasing
    assert train_df["date"].max() < test_df["date"].min()


def test_time_based_split_missing_date_raises():
    df = pd.DataFrame({"match_id": ["m1"], "odds_home": [1.9], "odds_draw": [3.2], "odds_away": [4.1], "actual_result": ["H"]})
    with pytest.raises(ValueError):
        time_based_split(df)


def test_time_based_split_invalid_date_raises():
    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "date": ["2025-01-01", "not-a-date"],
            "odds_home": [1.9, 2.1],
            "odds_draw": [3.2, 3.0],
            "odds_away": [4.1, 3.7],
            "actual_result": ["H", "A"],
        }
    )
    with pytest.raises(ValueError):
        time_based_split(df)
