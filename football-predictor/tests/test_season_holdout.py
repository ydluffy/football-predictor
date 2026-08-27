from __future__ import annotations

import pandas as pd

from evaluate.season_holdout import run_season_holdout


def test_run_season_holdout_uses_only_prior_seasons():
    rows = []
    for season_index, season in enumerate(["2021-22", "2022-23", "2023-24"]):
        for i in range(18):
            rows.append(
                {
                    "match_id": f"{season}-{i}",
                    "date": f"{2021 + season_index}-08-{i % 9 + 1:02d}",
                    "season": season,
                    "league": "E0",
                    "odds_home": 1.8 + (i % 3) * 0.2,
                    "odds_draw": 3.1 + (i % 2) * 0.1,
                    "odds_away": 3.0 + (i % 4) * 0.2,
                    "actual_result": ["H", "D", "A"][i % 3],
                }
            )
    df = pd.DataFrame(rows)
    out = run_season_holdout(df, feature_version="v1", model_type="logit", min_train_seasons=2)

    assert out["holdout_season"].tolist() == ["2023-24"]
    assert out.loc[0, "train_seasons"] == "2021-22,2022-23"
    assert out.loc[0, "train_size"] == 36
    assert out.loc[0, "test_size"] == 18
