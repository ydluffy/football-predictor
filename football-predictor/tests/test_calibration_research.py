from __future__ import annotations

import pandas as pd

from evaluate.calibration_research import run_calibration_research


def _matches() -> pd.DataFrame:
    rows = []
    outcomes = [("H", 2, 1), ("D", 1, 1), ("A", 0, 1)]
    for league in ("I1", "N1"):
        for season_index, season in enumerate(("2020-21", "2021-22", "2022-23")):
            for match_index in range(30):
                result, home_goals, away_goals = outcomes[match_index % 3]
                rows.append(
                    {
                        "match_id": f"{league}-{season}-{match_index}",
                        "league": league,
                        "season": season,
                        "date": f"{2020 + season_index}-09-{match_index + 1:02d}",
                        "home_team": f"{league} Home {match_index % 6}",
                        "away_team": f"{league} Away {match_index % 6}",
                        "home_goals": home_goals,
                        "away_goals": away_goals,
                        "actual_result": result,
                        "odds_home": 2.1 + 0.1 * (match_index % 3),
                        "odds_draw": 3.2,
                        "odds_away": 3.1 - 0.1 * (match_index % 3),
                    }
                )
    return pd.DataFrame(rows)


def test_calibration_research_is_per_competition_and_never_promotes() -> None:
    folds, summaries, skipped = run_calibration_research(
        _matches(),
        competition_labels=["I1", "N1"],
        min_train_seasons=2,
        n_bootstrap=100,
    )
    assert skipped == []
    assert set(folds["source_label"]) == {"I1", "N1"}
    assert len(summaries) == 2
    assert all(item["decision"] in {"shadow_eligible", "research_rejected"} for item in summaries)
    assert all("gates" in item for item in summaries)


def test_calibration_research_rejects_unsupported_model() -> None:
    try:
        run_calibration_research(
            _matches(),
            competition_labels=["I1"],
            model_type="lightgbm",
            n_bootstrap=100,
        )
    except ValueError as exc:
        assert "logit only" in str(exc)
    else:
        raise AssertionError("unsupported calibration model should fail")
