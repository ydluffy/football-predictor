from __future__ import annotations

import numpy as np
import pandas as pd

from data.transform_rules import standardize_dataset_values


def test_standardize_dataset_values_basic_conversions():
    df = pd.DataFrame(
        {
            "date": ["2025-01-01", "bad"],
            "injury_flag": ["1", "x"],
            "actual_result": ["H", "draw"],
            "odds_home": ["2.1", "bad"],
            "xg_home": ["1.4", None],
            "line_move": ["-0.05", "bad"],
        }
    )
    out = standardize_dataset_values(df)
    assert out["date"].dtype.name in {"string", "object"}
    assert str(out.loc[0, "date"]) == "2025-01-01"
    assert pd.isna(out.loc[1, "date"])

    assert int(out.loc[0, "injury_flag"]) == 1
    assert pd.isna(out.loc[1, "injury_flag"])

    assert out.loc[0, "actual_result"] == "home"
    assert out.loc[1, "actual_result"] == "draw"

    assert np.isclose(out.loc[0, "odds_home"], 2.1)
    assert np.isnan(out.loc[1, "odds_home"])
    assert np.isclose(out.loc[0, "line_move"], -0.05)
    assert np.isnan(out.loc[1, "line_move"])

