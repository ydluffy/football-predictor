from world_cup.halftime_trends import first_half_score_from_events
from world_cup.halftime_trends import summarize_halftime_trends

import pandas as pd


def test_first_half_score_from_events_counts_goals_and_own_goals():
    events = [
        {
            "period": 1,
            "type": {"name": "Shot"},
            "team": {"name": "Argentina"},
            "shot": {"outcome": {"name": "Goal"}},
        },
        {
            "period": 1,
            "type": {"name": "Own Goal For"},
            "team": {"name": "France"},
        },
        {
            "period": 2,
            "type": {"name": "Shot"},
            "team": {"name": "Argentina"},
            "shot": {"outcome": {"name": "Goal"}},
        },
    ]

    assert first_half_score_from_events(
        events,
        home_team="Argentina",
        away_team="France",
    ) == (1, 1)


def test_summarize_halftime_trends_splits_group_and_knockout():
    matches = pd.DataFrame(
        [
            {
                "stage_bucket": "group",
                "full_time_total_goals_90": 2,
                "half_time_total_goals": 0,
                "half_time_result": "D",
                "full_time_result_90": "H",
                "over_0_5_ht": 0,
                "over_1_5_ht": 0,
                "over_1_5_ft": 1,
                "over_2_5_ft": 0,
                "over_3_5_ft": 0,
                "both_teams_scored": 0,
                "season": "2022",
                "half_full_result": "D-H",
            },
            {
                "stage_bucket": "knockout",
                "full_time_total_goals_90": 3,
                "half_time_total_goals": 2,
                "half_time_result": "H",
                "full_time_result_90": "H",
                "over_0_5_ht": 1,
                "over_1_5_ht": 1,
                "over_1_5_ft": 1,
                "over_2_5_ft": 1,
                "over_3_5_ft": 0,
                "both_teams_scored": 1,
                "season": "2022",
                "half_full_result": "H-H",
            },
        ]
    )

    tables = summarize_halftime_trends(matches)

    assert set(tables["stage_summary"]["stage_bucket"]) == {"group", "knockout"}
    assert set(tables["half_full_distribution"]["half_full_result"]) == {"D-H", "H-H"}
