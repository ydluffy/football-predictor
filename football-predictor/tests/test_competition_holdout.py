from __future__ import annotations

import pandas as pd

from evaluate.competition_holdout import run_competition_season_holdouts, summarize_competition_holdouts


def _matches() -> pd.DataFrame:
    rows = []
    outcomes = [("H", 2, 1), ("D", 1, 1), ("A", 0, 1)]
    for league in ("E0", "SP1"):
        for season_index, season in enumerate(("2020-21", "2021-22", "2022-23")):
            for match_index in range(12):
                result, home_goals, away_goals = outcomes[match_index % 3]
                rows.append(
                    {
                        "match_id": f"{league}-{season}-{match_index}",
                        "league": league,
                        "season": season,
                        "date": f"{2020 + season_index}-09-{match_index + 1:02d}",
                        "home_team": f"{league} Home {match_index % 4}",
                        "away_team": f"{league} Away {match_index % 4}",
                        "home_goals": home_goals,
                        "away_goals": away_goals,
                        "actual_result": result,
                        "odds_home": 2.2 + 0.05 * (match_index % 3),
                        "odds_draw": 3.1,
                        "odds_away": 3.2 - 0.05 * (match_index % 3),
                    }
                )
    return pd.DataFrame(rows)


def test_competition_holdout_keeps_leagues_independent() -> None:
    results, skipped = run_competition_season_holdouts(_matches(), min_train_seasons=2)

    assert skipped == []
    assert set(results["competition_id"]) == {"ENG_PREMIER_LEAGUE", "ESP_LA_LIGA"}
    assert set(results["holdout_season"]) == {"2022-23"}
    assert len(results) == 2


def test_competition_holdout_summary_never_promotes_models() -> None:
    results, _ = run_competition_season_holdouts(_matches(), min_train_seasons=2)
    summary = summarize_competition_holdouts(results)

    assert len(summary) == 2
    assert all(item["decision"] in {"calibration_research_eligible", "not_promoted"} for item in summary)
