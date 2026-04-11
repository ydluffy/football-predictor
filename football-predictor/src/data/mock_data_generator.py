from __future__ import annotations

import pandas as pd

from ingest.data_foundation import generate_mock_matches as _generate_base


def generate_mock_matches(n_rows: int = 200, feature_version: str = "v3") -> pd.DataFrame:
    fv = str(feature_version)
    if fv not in {"v1", "v2", "v3"}:
        raise ValueError("feature_version 仅支持 v1/v2/v3")

    df = _generate_base(n=int(n_rows), seed=42, start_date="2025-01-01", include_optional=True)

    base_cols = [
        "match_id",
        "date",
        "league",
        "home_team",
        "away_team",
        "odds_home",
        "odds_draw",
        "odds_away",
        "actual_result",
    ]
    v2_cols = base_cols + ["xg_home", "xg_away", "injury_flag", "line_move"]
    v3_cols = v2_cols + [
        "odds_home_open",
        "odds_draw_open",
        "odds_away_open",
        "odds_home_last",
        "odds_draw_last",
        "odds_away_last",
        "home_xg_last_1",
        "home_xg_last_2",
        "home_xg_last_3",
        "away_xg_last_1",
        "away_xg_last_2",
        "away_xg_last_3",
        "home_xga_last_1",
        "home_xga_last_2",
        "home_xga_last_3",
        "away_xga_last_1",
        "away_xga_last_2",
        "away_xga_last_3",
    ]

    keep = base_cols if fv == "v1" else v2_cols if fv == "v2" else v3_cols
    keep = [c for c in keep if c in df.columns]
    return df[keep].copy()

