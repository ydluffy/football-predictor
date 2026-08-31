from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "research_sporttery_results_patterns.py"
SPEC = importlib.util.spec_from_file_location("research_sporttery_results_patterns", MODULE_PATH)
research = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(research)


def test_result_pattern_derived_fields(tmp_path):
    path = tmp_path / "world_cup.csv"
    pd.DataFrame(
        [
            {
                "match_number": "095",
                "date": "2026-07-08",
                "home_team": "Argentina",
                "home_handicap": -1,
                "away_team": "Egypt",
                "half_time_score": "0-2",
                "full_time_90_score": "3-2",
                "spf_home_odds": 1.22,
                "spf_draw_odds": 4.72,
                "spf_away_odds": 10.25,
            }
        ]
    ).to_csv(path, index=False)

    frame = research.load_world_cup(path)
    row = frame.iloc[0]

    assert row["total_goals"] == 5
    assert row["spf_result"] == "胜"
    assert row["rqspf_result"] == "让平"
    assert row["half_full"] == "A-H"
    assert row["favorite"] == "home"
    assert row["favorite_result"] == "hit"
