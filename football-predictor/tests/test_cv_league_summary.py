from __future__ import annotations

import pandas as pd
import pytest

from evaluate.cv_league_summary import summarize_cv_by_league


def test_summarize_cv_by_league_normal_case():
    df = pd.DataFrame(
        {
            "model_type": ["logit"] * 6,
            "feature_version": ["v2"] * 6,
            "fold": [0, 0, 0, 1, 1, 1],
            "league": ["EPL", "EPL", "LaLiga", "EPL", "LaLiga", "LaLiga"],
            "actual": ["H", "D", "A", "H", "D", "A"],
            "p_home": [0.6, 0.2, 0.1, 0.5, 0.3, 0.2],
            "p_draw": [0.2, 0.6, 0.2, 0.3, 0.4, 0.3],
            "p_away": [0.2, 0.2, 0.7, 0.2, 0.3, 0.5],
        }
    )
    out = summarize_cv_by_league(df)
    assert {"model_type", "feature_version", "fold", "league", "n_samples", "brier", "logloss"} <= set(out.columns)
    assert out["n_samples"].sum() == len(df)
    assert out["brier"].notna().all()
    assert out["logloss"].notna().all()


def test_summarize_cv_by_league_missing_league_raises():
    df = pd.DataFrame(
        {
            "model_type": ["logit"],
            "feature_version": ["v2"],
            "fold": [0],
            "actual": ["H"],
            "p_home": [0.6],
            "p_draw": [0.2],
            "p_away": [0.2],
        }
    )
    with pytest.raises(ValueError):
        summarize_cv_by_league(df)


def test_summarize_cv_by_league_allows_small_sample():
    df = pd.DataFrame(
        {
            "model_type": ["logit", "logit"],
            "feature_version": ["v2", "v2"],
            "fold": [0, 0],
            "league": ["TinyLeague", "EPL"],
            "actual": ["H", "D"],
            "p_home": [0.6, 0.1],
            "p_draw": [0.2, 0.7],
            "p_away": [0.2, 0.2],
        }
    )
    out = summarize_cv_by_league(df)
    tiny = out.loc[out["league"] == "TinyLeague"]
    assert len(tiny) == 1
    assert int(tiny["n_samples"].iloc[0]) == 1

