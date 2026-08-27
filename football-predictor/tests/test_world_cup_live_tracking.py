from __future__ import annotations

import pandas as pd

from world_cup.live_tracking import (
    combine_completed_results,
    goal_environment_report,
    settle_predictions,
    summarize_settled_predictions,
)


def test_manual_result_override_replaces_upstream_result():
    upstream = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-06-14"),
                "home_team": "A",
                "away_team": "B",
                "home_goals": 1,
                "away_goals": 1,
                "actual_result": "D",
                "tournament": "FIFA World Cup",
            }
        ]
    )
    override = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-06-14"),
                "home_team": "A",
                "away_team": "B",
                "home_goals": 2,
                "away_goals": 1,
                "result_source": "manual_verified",
                "source_url": "https://example.test/result",
            }
        ]
    )

    out = combine_completed_results(upstream, override)

    assert len(out) == 1
    assert out.loc[0, "actual_result"] == "H"
    assert out.loc[0, "home_goals"] == 2
    assert out.loc[0, "result_source"] == "manual_verified"


def test_settle_predictions_keeps_pending_and_calculates_metrics():
    predictions = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-06-14"),
                "home_team": "A",
                "away_team": "B",
                "p_home": 0.6,
                "p_draw": 0.25,
                "p_away": 0.15,
                "expected_home_goals": 1.8,
                "expected_away_goals": 0.7,
                "most_likely_home_goals": 2,
                "most_likely_away_goals": 0,
                "model_variant": "baseline",
            },
            {
                "date": pd.Timestamp("2026-06-15"),
                "home_team": "C",
                "away_team": "D",
                "p_home": 0.4,
                "p_draw": 0.3,
                "p_away": 0.3,
                "expected_home_goals": 1.2,
                "expected_away_goals": 1.0,
                "most_likely_home_goals": 1,
                "most_likely_away_goals": 1,
                "model_variant": "baseline",
            },
        ]
    )
    results = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-06-14"),
                "home_team": "A",
                "away_team": "B",
                "home_goals": 2,
                "away_goals": 0,
                "actual_result": "H",
                "tournament": "FIFA World Cup",
                "result_source": "manual_verified",
                "source_url": "",
            }
        ]
    )

    settled = settle_predictions(predictions, results)
    summary = summarize_settled_predictions(settled)

    assert settled["settled"].tolist() == [True, False]
    assert settled.loc[0, "correct"]
    assert settled.loc[0, "exact_score"]
    assert summary["settled_matches"] == 1
    assert summary["pending_predictions"] == 1
    assert summary["accuracy"] == 1.0


def test_goal_environment_detects_high_scoring_current_tournament():
    rows = []
    for year in (2010, 2014, 2018, 2022):
        rows.append(
            {
                "date": pd.Timestamp(f"{year}-06-10"),
                "home_team": "A",
                "away_team": "B",
                "home_goals": 1,
                "away_goals": 1,
                "actual_result": "D",
                "tournament": "FIFA World Cup",
                "result_source": "test",
                "source_url": "",
            }
        )
    rows.append(
        {
            "date": pd.Timestamp("2026-06-14"),
            "home_team": "A",
            "away_team": "B",
            "home_goals": 4,
            "away_goals": 1,
            "actual_result": "H",
            "tournament": "FIFA World Cup",
            "result_source": "test",
            "source_url": "",
        }
    )

    report = goal_environment_report(pd.DataFrame(rows))

    assert report["historical_goals_per_match"] == 2.0
    assert report["current_goals_per_match"] == 5.0
    assert report["status"] == "higher_scoring"
