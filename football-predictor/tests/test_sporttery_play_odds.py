from __future__ import annotations

import pandas as pd

from world_cup.sporttery_play_odds import find_play_odds
from world_cup.sporttery_play_odds import flatten_play_market_value
from world_cup.sporttery_play_odds import latest_sporttery_play_odds
from world_cup.sporttery_play_odds import load_sporttery_play_odds
from world_cup.sporttery_play_odds import normalize_correct_score_selection
from world_cup.sporttery_play_odds import normalize_total_goals_selection
from world_cup.sporttery_play_odds import parse_lottery_gov_correct_score_text
from world_cup.sporttery_play_odds import parse_lottery_gov_half_full_time_text
from world_cup.sporttery_play_odds import parse_lottery_gov_total_goals_text
from world_cup.sporttery_play_odds import play_market_value
from world_cup.sporttery_play_odds import total_goals_model_probabilities


def test_normalize_total_goals_selection():
    assert normalize_total_goals_selection("0") == "0"
    assert normalize_total_goals_selection("7+") == "7_plus"
    assert normalize_total_goals_selection("7球及以上") == "7_plus"


def test_load_and_find_latest_total_goals_odds(tmp_path):
    path = tmp_path / "sporttery_play_odds.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-07-04",
                "match_id": "760001",
                "match_number": "001",
                "home_team": "Canada",
                "away_team": "Morocco",
                "play_type": "total_goals",
                "selection": "1",
                "odds": 3.4,
                "source": "sporttery_manual",
                "snapshot_type": "opening",
                "captured_at": "2026-07-04T10:00:00+08:00",
                "notes": "",
            },
            {
                "date": "2026-07-04",
                "match_id": "760001",
                "match_number": "001",
                "home_team": "Canada",
                "away_team": "Morocco",
                "play_type": "total_goals",
                "selection": "1",
                "odds": 3.6,
                "source": "sporttery_manual",
                "snapshot_type": "latest",
                "captured_at": "2026-07-04T18:00:00+08:00",
                "notes": "",
            },
            {
                "date": "2026-07-04",
                "match_id": "760001",
                "match_number": "001",
                "home_team": "Canada",
                "away_team": "Morocco",
                "play_type": "total_goals",
                "selection": "2",
                "odds": 3.2,
                "source": "sporttery_manual",
                "snapshot_type": "latest",
                "captured_at": "2026-07-04T18:00:00+08:00",
                "notes": "",
            },
        ]
    ).to_csv(path, index=False)

    odds = load_sporttery_play_odds(path)
    latest = latest_sporttery_play_odds(odds)
    found = find_play_odds(
        odds,
        date="2026-07-04",
        home_team="Canada",
        away_team="Morocco",
        play_type="total_goals",
    )

    assert len(latest) == 2
    assert found == {"1": 3.6, "2": 3.2}


def test_find_play_odds_allows_one_day_date_gap(tmp_path):
    path = tmp_path / "sporttery_play_odds.csv"
    pd.DataFrame(
        [
                {
                    "date": "2026-07-05",
                    "match_id": "",
                    "match_number": "089",
                    "home_team": "Canada",
                    "away_team": "Morocco",
                "play_type": "total_goals",
                "selection": "1",
                "odds": 4.3,
            }
        ]
    ).to_csv(path, index=False)

    odds = load_sporttery_play_odds(path)
    found = find_play_odds(
        odds,
        date="2026-07-04",
        home_team="Canada",
        away_team="Morocco",
        play_type="total_goals",
    )

    assert found == {"1": 4.3}


def test_play_market_value_ranks_expected_value():
    out = play_market_value(
        {"1": 0.40, "2": 0.20, "3": 0.40},
        {"1": 3.00, "2": 4.00, "3": 2.00},
    )

    assert out["best_selection"] == "1"
    assert round(out["best_expected_value"], 3) == 0.2
    assert out["rows"][0]["edge"] > 0


def test_total_goals_model_probabilities_and_flatten_value():
    probabilities = total_goals_model_probabilities(
        {
            "sporttery_total_goal_probabilities": {
                "total_goals_0_probability": 0.1,
                "total_goals_1_probability": 0.4,
                "total_goals_7_plus_probability": 0.05,
            }
        }
    )
    value = play_market_value(
        probabilities,
        {"0": 8.0, "1": 3.0, "7_plus": 20.0},
    )
    flat = flatten_play_market_value(
        value,
        prefix="sporttery_total_goals",
        selections=["0", "1", "7_plus"],
    )

    assert probabilities == {"0": 0.1, "1": 0.4, "7_plus": 0.05}
    assert flat["sporttery_total_goals_best_selection"] == "1"
    assert flat["sporttery_total_goals_value_signal"] == "positive"
    assert flat["sporttery_total_goals_7_plus_odds"] == 20.0


def test_parse_lottery_gov_total_goals_text():
    text = "\n".join(
        [
            "周六",
            "089\t世界杯\t07-05",
            "01:00\t[世界杯2]加拿大VS摩洛哥[世界杯2]\t9.504.302.903.407.0014.0027.0038.00\t同奖",
        ]
    )

    out = parse_lottery_gov_total_goals_text(
        text,
        captured_at="2026-07-04T20:00:00+08:00",
    )

    assert len(out) == 8
    assert out.loc[0, "date"] == "2026-07-05"
    assert out.loc[0, "home_team"] == "加拿大"
    assert out.loc[0, "away_team"] == "摩洛哥"
    assert out.loc[0, "play_type"] == "total_goals"
    assert out.loc[0, "selection"] == "0"
    assert out.loc[7, "selection"] == "7_plus"
    assert out.loc[7, "odds"] == 38.0


def test_parse_lottery_gov_half_full_time_text():
    text = "\n".join(
        [
            "周六",
            "089\t世界杯\t07-05",
            "01:00\t[世界杯2]加拿大VS摩洛哥[世界杯2]\t8.5013.5020.0010.505.164.1532.0013.502.65\t半场全场",
        ]
    )

    out = parse_lottery_gov_half_full_time_text(text)

    assert len(out) == 9
    assert out.loc[0, "play_type"] == "half_full_time"
    assert out.loc[0, "selection"] == "H-H"
    assert out.loc[5, "selection"] == "D-A"
    assert out.loc[8, "odds"] == 2.65


def test_normalize_correct_score_selection():
    assert normalize_correct_score_selection("1:0") == "1:0"
    assert normalize_correct_score_selection("胜其它") == "home_other"
    assert normalize_correct_score_selection("平其他") == "draw_other"
    assert normalize_correct_score_selection("负其它") == "away_other"


def test_parse_lottery_gov_correct_score_text():
    text = "\n".join(
        [
            "周六089\t世界杯\t07-05 01:00\t[世界杯2]加拿大 VS 摩洛哥[世界杯2]\t同奖",
            "------",
            "胜",
            "1:0",
            "12.50",
            "2:0",
            "28.00",
            "胜其它",
            "400.0",
            "平",
            "0:0",
            "9.50",
            "1:1",
            "5.80",
            "平其它",
            "400.0",
            "负",
            "0:1",
            "5.95",
            "负其它",
            "100.0",
            "周六090\t世界杯\t07-05 05:00\t[世界杯3]巴拉圭 VS 法国[世界杯1]\t同奖",
            "------",
        ]
    )

    out = parse_lottery_gov_correct_score_text(
        text,
        captured_at="2026-07-04T20:30:00+08:00",
    )

    assert len(out) == 8
    assert out.loc[0, "date"] == "2026-07-05"
    assert out.loc[0, "home_team"] == "加拿大"
    assert out.loc[0, "away_team"] == "摩洛哥"
    assert out.loc[0, "play_type"] == "correct_score"
    assert set(out["selection"]) == {
        "1:0",
        "2:0",
        "home_other",
        "0:0",
        "1:1",
        "draw_other",
        "0:1",
        "away_other",
    }
