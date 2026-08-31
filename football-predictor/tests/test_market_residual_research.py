from __future__ import annotations

import pandas as pd

from evaluate.market_residual_research import run_market_residual_research


def _matches() -> pd.DataFrame:
    rows = []
    outcomes = [("H", 2, 1), ("D", 1, 1), ("A", 0, 1)]
    for season_index, season in enumerate(("2020-21", "2021-22", "2022-23")):
        for match_index in range(30):
            result, home_goals, away_goals = outcomes[match_index % 3]
            rows.append(
                {
                    "match_id": f"I1-{season}-{match_index}",
                    "league": "I1",
                    "season": season,
                    "date": f"{2020 + season_index}-09-{match_index + 1:02d}",
                    "home_team": f"Home {match_index % 6}",
                    "away_team": f"Away {match_index % 6}",
                    "home_goals": home_goals,
                    "away_goals": away_goals,
                    "actual_result": result,
                    "odds_home": 2.1 + 0.1 * (match_index % 3),
                    "odds_draw": 3.2,
                    "odds_away": 3.1 - 0.1 * (match_index % 3),
                }
            )
    return pd.DataFrame(rows)


def test_nested_market_residual_research_never_promotes() -> None:
    folds, summaries, skipped = run_market_residual_research(
        _matches(), competition_labels=["I1"], n_bootstrap=100
    )
    assert skipped == []
    assert len(folds) == 1
    assert len(summaries) == 1
    assert summaries[0]["decision"] in {"shadow_eligible", "research_rejected"}
    assert summaries[0]["context_feature_count"] > 0
    assert 0.0 <= folds.iloc[0]["selected_strength"] <= 1.0
