from __future__ import annotations

import pandas as pd

from config.settings import get_settings
from research_director.agents.data_scout_agent import DataScoutAgent


def test_data_scout_keep_actual_result_true_does_not_blank(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    raw = s.data_external_dir
    raw.mkdir(parents=True, exist_ok=True)
    inp = raw / "one.csv"
    pd.DataFrame(
        {
            "date": ["2025-01-01"],
            "league": ["EPL"],
            "home_team": ["A"],
            "away_team": ["B"],
            "odds_home": [2.0],
            "odds_draw": [3.0],
            "odds_away": [4.0],
            "actual_result": ["H"],
        }
    ).to_csv(inp, index=False)

    run_dir = s.research_director_runs_dir / "r1"
    out_path = run_dir / "real_matches_standardized.csv"

    agent = DataScoutAgent()
    res = agent.execute(
        context={
            "run_id": "r1",
            "run_dir": str(run_dir),
            "raw_matches_csv": str(inp),
            "feature_version": "v1",
            "keep_actual_result": True,
            "output_csv_path": str(out_path),
        },
        gate=object(),
    )
    assert res.status == "completed"
    df = pd.read_csv(out_path)
    assert df.loc[0, "actual_result"] == "H"


def test_data_scout_multi_source_concat(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    s = get_settings()

    ext = s.data_external_dir
    ext.mkdir(parents=True, exist_ok=True)

    a = ext / "a.csv"
    b = ext / "b.csv"
    pd.DataFrame(
        {
            "match_id": ["m1"],
            "date": ["2025-01-01"],
            "league": ["EPL"],
            "home_team": ["A"],
            "away_team": ["B"],
            "odds_home": [2.0],
            "odds_draw": [3.0],
            "odds_away": [4.0],
            "actual_result": ["H"],
        }
    ).to_csv(a, index=False)
    pd.DataFrame(
        {
            "match_id": ["m2"],
            "date": ["2025-01-02"],
            "league": ["EPL"],
            "home_team": ["C"],
            "away_team": ["D"],
            "odds_home": [2.2],
            "odds_draw": [3.1],
            "odds_away": [3.8],
            "actual_result": ["D"],
        }
    ).to_csv(b, index=False)

    run_dir = s.research_director_runs_dir / "r2"
    out_path = run_dir / "real_matches_standardized.csv"

    agent = DataScoutAgent()
    res = agent.execute(
        context={
            "run_id": "r2",
            "run_dir": str(run_dir),
            "feature_version": "v1",
            "keep_actual_result": True,
            "output_csv_path": str(out_path),
            "data_sources": [{"raw_matches_csv": str(a)}, {"raw_matches_csv": str(b)}],
        },
        gate=object(),
    )
    assert res.status == "completed"
    df = pd.read_csv(out_path)
    assert len(df) == 2
    assert set(df["match_id"].astype(str).tolist()) == {"m1", "m2"}

