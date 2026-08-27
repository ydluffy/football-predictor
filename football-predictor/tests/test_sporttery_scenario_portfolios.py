from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "review_sporttery_scenario_portfolios.py"
SPEC = importlib.util.spec_from_file_location("review_sporttery_scenario_portfolios", MODULE_PATH)
review = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(review)

BUILD_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_sporttery_scenario_portfolios.py"
BUILD_SPEC = importlib.util.spec_from_file_location("build_sporttery_scenario_portfolios", BUILD_MODULE_PATH)
builder = importlib.util.module_from_spec(BUILD_SPEC)
assert BUILD_SPEC and BUILD_SPEC.loader
sys.modules[BUILD_SPEC.name] = builder
BUILD_SPEC.loader.exec_module(builder)


def test_evaluate_scenario_ticket_types():
    result = pd.Series(
        {
            "half_time_score": "0:0",
            "full_time_score": "1:2",
            "handicap": -1,
        }
    )

    assert review.evaluate_ticket("主判断｜胜平负主方向｜胜@2.36｜28元(28元/项)", result)["hit"] is False
    assert review.evaluate_ticket("防线｜英格兰-1让球防线｜让负@1.45/让平@3.8｜20元(10元/项)", result)["hit"] is True
    assert review.evaluate_ticket("进球｜总进球双选｜2@3.2/3@3.7｜24元(12元/项)", result)["payout"] == 44.4
    assert review.evaluate_ticket("比分｜比分防冷多选｜1:1@5.15/0:1@8.85/1:2@9.5｜18元(6元/项)", result)["payout"] == 57.0
    assert review.evaluate_ticket("半全场｜半全场进程｜D-A@4/A-A@2.46｜8元(4元/项)", result)["payout"] == 16.0


def test_review_portfolios_sums_independent_same_match_tickets():
    portfolios = pd.DataFrame(
        [
            {
                "plan_id": "SCENARIO_102",
                "match_number": "102",
                "match": "英格兰 vs 阿根廷",
                "tickets": (
                    "主判断｜胜平负主方向｜胜@2.36｜28元(28元/项)；"
                    "防线｜英格兰-1让球防线｜让负@1.45/让平@3.8｜20元(10元/项)；"
                    "比分｜比分防冷多选｜1:1@5.15/0:1@8.85/1:2@9.5｜18元(6元/项)"
                ),
            }
        ]
    )
    results = pd.DataFrame(
        [
            {
                "match_number": "周三102",
                "half_time_score": "0:0",
                "full_time_score": "1:2",
                "handicap": -1,
            }
        ]
    )

    summary, details = review.review_portfolios(portfolios, results)

    assert summary.loc[0, "stake"] == 66.0
    assert summary.loc[0, "payout"] == 71.5
    assert summary.loc[0, "net"] == 5.5
    assert summary.loc[0, "hit_tickets"] == 2
    assert len(details) == 3


def test_high_risk_signal_rebalances_same_match_package():
    markets = pd.DataFrame(
        [
            {
                "match_number": "103",
                "kickoff_time": "2026-07-19 03:00",
                "home_team": "法国",
                "away_team": "英格兰",
                "home_handicap": -1,
                "spf_odds_home": 1.70,
                "spf_odds_draw": 3.80,
                "spf_odds_away": 3.60,
                "rqspf_odds_home": 3.08,
                "rqspf_odds_draw": 3.70,
                "rqspf_odds_away": 1.87,
                "market_signal_strength": "high_risk",
                "market_risk_flags": "sporttery_deeper_than_external,external_shallow_vs_sporttery_deep",
                "market_signal_note": "体彩比外盘更激进，优先防热和赢球不穿。",
                "external_latest_total_signal": "over",
            }
        ]
    )
    play_odds = pd.DataFrame(
        [
            {"match_number": "103", "home_team": "法国", "away_team": "英格兰", "play_type": "total_goals", "selection": "2", "odds": 3.2},
            {"match_number": "103", "home_team": "法国", "away_team": "英格兰", "play_type": "total_goals", "selection": "3", "odds": 3.7},
            {"match_number": "103", "home_team": "法国", "away_team": "英格兰", "play_type": "correct_score", "selection": "1:0", "odds": 6.5},
            {"match_number": "103", "home_team": "法国", "away_team": "英格兰", "play_type": "correct_score", "selection": "2:1", "odds": 7.5},
            {"match_number": "103", "home_team": "法国", "away_team": "英格兰", "play_type": "correct_score", "selection": "1:1", "odds": 5.5},
            {"match_number": "103", "home_team": "法国", "away_team": "英格兰", "play_type": "half_full_time", "selection": "D-H", "odds": 4.2},
            {"match_number": "103", "home_team": "法国", "away_team": "英格兰", "play_type": "half_full_time", "selection": "D-D", "odds": 5.0},
        ]
    )

    frame = builder.build_portfolios(markets, play_odds, 100)

    tickets = frame.loc[0, "tickets"]
    assert frame.loc[0, "market_signal_strength"] == "high_risk"
    assert "主判断｜胜平负主方向｜胜@1.7｜18元" in tickets
    assert "热门让球防线" in tickets
    assert "让负@1.87/让平@3.7｜24元" in tickets
    assert "1:0@6.5/2:1@7.5/1:1@5.5" in tickets


def test_scenario_package_drops_zero_odds_tickets():
    markets = pd.DataFrame(
        [
            {
                "match_number": "203",
                "kickoff_time": "2026-07-18 01:15",
                "home_team": "博德闪耀",
                "away_team": "腓特烈",
                "home_handicap": -2,
                "spf_odds_home": 0,
                "spf_odds_draw": 0,
                "spf_odds_away": 0,
                "rqspf_odds_home": 2.4,
                "rqspf_odds_draw": 4.15,
                "rqspf_odds_away": 3.0,
            }
        ]
    )

    frame = builder.build_portfolios(markets, pd.DataFrame(), 100)

    assert "胜平负主方向" not in frame.loc[0, "tickets"]
    assert frame.loc[0, "ticket_count"] == 1
