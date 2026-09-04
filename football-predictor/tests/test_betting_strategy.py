from __future__ import annotations

import pandas as pd

from world_cup.betting_strategy import BettingPlan
from world_cup.betting_strategy import StrategyLeg
from world_cup.betting_strategy import build_multi_play_plans
from world_cup.betting_strategy import classify_match


def test_betting_plan_counts_multi_selection_bets() -> None:
    plan = BettingPlan(
        plan_id="T",
        plan_type="防冷",
        title="test",
        stake=100,
        legs=(
            StrategyLeg("101", "法国 vs 西班牙", "胜平负", (("主胜", 2.0), ("平", 3.0))),
            StrategyLeg("201", "杰尔 vs 雷克维京", "让球胜平负", (("让负", 1.8),)),
        ),
        rationale="",
        risk_notes="",
    )

    assert plan.bet_count == 2
    assert plan.amount_per_bet == 50
    assert plan.total_stake == 100
    assert plan.unused_budget == 0
    assert plan.multiplier == 25
    assert plan.odds_range == (3.6, 5.4)
    assert plan.payout_range == (180.0, 270.0)


def test_betting_plan_uses_two_yuan_unit_without_exceeding_budget() -> None:
    plan = BettingPlan(
        plan_id="T4",
        plan_type="防冷",
        title="test",
        stake=100,
        legs=(
            StrategyLeg("101", "法国 vs 西班牙", "胜平负", (("主胜", 2.0), ("平", 3.0))),
            StrategyLeg("201", "杰尔 vs 雷克维京", "胜平负", (("主胜", 1.8), ("平", 3.7))),
        ),
        rationale="",
        risk_notes="",
    )

    assert plan.bet_count == 4
    assert plan.multiplier == 12
    assert plan.amount_per_bet == 24
    assert plan.total_stake == 96
    assert plan.unused_budget == 4


def test_build_multi_play_plans_from_market_rows() -> None:
    markets = pd.DataFrame(
        [
            {
                "match_number": "101",
                "competition": "世界杯",
                "kickoff_time": "2026-07-15 03:00",
                "home_team": "法国",
                "away_team": "西班牙",
                "home_handicap": "-1",
                "spf_odds_home": 2.03,
                "spf_odds_draw": 3.13,
                "spf_odds_away": 3.15,
                "rqspf_odds_home": 4.33,
                "rqspf_odds_draw": 3.60,
                "rqspf_odds_away": 1.61,
            },
            {
                "match_number": "201",
                "competition": "欧冠",
                "kickoff_time": "2026-07-15 01:00",
                "home_team": "杰尔",
                "away_team": "雷克维京",
                "home_handicap": "-1",
                "spf_odds_home": 1.69,
                "spf_odds_draw": 3.70,
                "spf_odds_away": 3.75,
                "rqspf_odds_home": 3.12,
                "rqspf_odds_draw": 3.50,
                "rqspf_odds_away": 1.91,
            },
        ]
    )

    match_rows, plans = build_multi_play_plans(
        markets,
        stake=100,
        fixed_odds_min=1.65,
        fixed_odds_max=1.75,
        fixed_odds_target=1.69,
        fixed_odds_max_legs=2,
    )

    assert len(match_rows) == 2
    assert {plan.plan_type for plan in plans} == {"防冷", "博高", "固定赔率观察"}
    assert all(plan.is_shadow for plan in plans)
    assert match_rows[0]["handicap_probability_source"] == "market_implied_only"
    fixed = next(plan for plan in plans if plan.plan_type == "固定赔率观察")
    assert fixed.plan_id == "MULTI_PLAY_FIXED_ODDS_SHADOW"
    assert fixed.odds_range == (1.69, 1.69)
    assert "不得自动写入真实投注台账" in fixed.risk_notes


def test_fixed_odds_observation_is_omitted_when_no_combination_is_in_band() -> None:
    markets = pd.DataFrame(
        [
            {
                "match_number": "101", "home_team": "A", "away_team": "B", "home_handicap": -1,
                "spf_odds_home": 1.20, "spf_odds_draw": 6.0, "spf_odds_away": 12.0,
                "rqspf_odds_home": 1.30, "rqspf_odds_draw": 5.0, "rqspf_odds_away": 8.0,
            }
        ]
    )

    _, plans = build_multi_play_plans(
        markets,
        fixed_odds_min=1.80,
        fixed_odds_max=2.00,
        fixed_odds_target=1.90,
    )

    assert all(plan.plan_type != "固定赔率观察" for plan in plans)


def test_default_fixed_odds_observation_targets_six_to_ten() -> None:
    markets = pd.DataFrame(
        [
            {
                "match_number": number, "home_team": f"H{number}", "away_team": f"A{number}",
                "home_handicap": -1, "spf_odds_home": 2.1, "spf_odds_draw": 3.2,
                "spf_odds_away": 3.4, "rqspf_odds_home": 2.0,
                "rqspf_odds_draw": 3.0, "rqspf_odds_away": 3.0,
            }
            for number in (1, 2, 3)
        ]
    )

    _, plans = build_multi_play_plans(markets, max_matches=3)

    fixed = next(plan for plan in plans if plan.plan_type == "固定赔率观察")
    assert 6.0 <= fixed.odds_range[0] <= 10.0
    assert len(fixed.legs) == 3


def test_high_risk_market_signal_demotes_deep_favorite_from_safe_plan() -> None:
    markets = pd.DataFrame(
        [
            {
                "match_number": "103",
                "competition": "世界杯",
                "kickoff_time": "2026-07-19 03:00",
                "home_team": "法国",
                "away_team": "英格兰",
                "home_handicap": "-1",
                "spf_odds_home": 1.70,
                "spf_odds_draw": 3.80,
                "spf_odds_away": 3.60,
                "rqspf_odds_home": 3.08,
                "rqspf_odds_draw": 3.70,
                "rqspf_odds_away": 1.87,
                "market_signal_strength": "high_risk",
                "market_risk_flags": "sporttery_deeper_than_external,external_shallow_vs_sporttery_deep",
                "market_signal_note": "体彩比外盘更激进，优先防热和赢球不穿。",
            },
            {
                "match_number": "201",
                "competition": "瑞超",
                "kickoff_time": "2026-07-18 18:30",
                "home_team": "哥德堡",
                "away_team": "布鲁马波",
                "home_handicap": "-1",
                "spf_odds_home": 1.50,
                "spf_odds_draw": 3.80,
                "spf_odds_away": 5.00,
                "rqspf_odds_home": 2.60,
                "rqspf_odds_draw": 3.40,
                "rqspf_odds_away": 2.20,
                "market_signal_strength": "medium_unknown",
                "market_risk_flags": "no_external_market",
            },
        ]
    )

    match_rows, plans = build_multi_play_plans(markets, stake=100)

    assert match_rows[0]["market_signal_strength"] == "high_risk"
    assert match_rows[0]["correct_score_suggestion"] == "1:0/2:1/1:1/2:0"
    production = [plan for plan in plans if not plan.is_shadow]
    assert all("103 法国 vs 英格兰" not in leg.selection_text for plan in production for leg in plan.legs)
    assert all("盘口信号" in plan.risk_notes for plan in plans if plan.plan_id in {"MULTI_PLAY_HEDGE", "MULTI_PLAY_HIGH"})


def test_build_multi_play_plans_skips_unpriced_rows() -> None:
    markets = pd.DataFrame(
        [
            {
                "match_number": "099",
                "competition": "世界杯",
                "kickoff_time": "2026-07-19 01:00",
                "home_team": "未开售",
                "away_team": "示例",
                "home_handicap": "-1",
                "spf_odds_home": "",
                "spf_odds_draw": "",
                "spf_odds_away": "",
                "rqspf_odds_home": "",
                "rqspf_odds_draw": "",
                "rqspf_odds_away": "",
            },
            {
                "match_number": "103",
                "competition": "世界杯",
                "kickoff_time": "2026-07-19 03:00",
                "home_team": "法国",
                "away_team": "英格兰",
                "home_handicap": "-1",
                "spf_odds_home": 1.70,
                "spf_odds_draw": 3.80,
                "spf_odds_away": 3.60,
                "rqspf_odds_home": 3.08,
                "rqspf_odds_draw": 3.70,
                "rqspf_odds_away": 1.87,
            },
        ]
    )

    match_rows, plans = build_multi_play_plans(markets, stake=100)

    assert len(match_rows) == 1
    assert match_rows[0]["match_number"] == "103"
    assert plans


def test_controlled_handicap_model_blend_changes_rqspf_ranking():
    row = pd.Series(
        {
            "match_number": "301", "home_team": "A", "away_team": "B", "home_handicap": -1,
            "spf_odds_home": 1.8, "spf_odds_draw": 3.5, "spf_odds_away": 4.0,
            "rqspf_odds_home": 2.8, "rqspf_odds_draw": 3.2, "rqspf_odds_away": 2.2,
            "handicap_model_usage": "production_auxiliary",
            "handicap_blended_probability_home": 0.55,
            "handicap_blended_probability_draw": 0.25,
            "handicap_blended_probability_away": 0.20,
            "handicap_model_pick": "home",
        }
    )
    classified = classify_match(row)
    assert classified["rqspf_rank"][0][0] == "home"
    assert classified["handicap_model_usage"] == "production_auxiliary"
    assert classified["handicap_probability_source"] == "model_blended"
    assert classified["handicap_production_eligible"] is True


def test_market_only_handicap_cannot_become_production_selection() -> None:
    markets = pd.DataFrame([
        {
            "match_number": str(number), "home_team": f"H{number}", "away_team": f"A{number}",
            "home_handicap": -1, "spf_odds_home": odd, "spf_odds_draw": 4.2,
            "spf_odds_away": 6.0, "rqspf_odds_home": 3.0,
            "rqspf_odds_draw": 3.4, "rqspf_odds_away": 1.75,
        }
        for number, odd in [(1, 1.45), (2, 1.55), (3, 1.65)]
    ])
    _, plans = build_multi_play_plans(markets, max_matches=3)
    production = [plan for plan in plans if not plan.is_shadow]
    assert production
    assert all(leg.play_type == "胜平负" for plan in production for leg in plan.legs)
    assert all("让负" not in leg.selection_text for plan in production for leg in plan.legs)


def test_safe_and_value_share_at_most_one_match() -> None:
    markets = pd.DataFrame([
        {
            "match_number": str(number), "home_team": f"H{number}", "away_team": f"A{number}",
            "home_handicap": -1, "spf_odds_home": odd, "spf_odds_draw": 4.5,
            "spf_odds_away": 7.0, "rqspf_odds_home": 3.0,
            "rqspf_odds_draw": 3.4, "rqspf_odds_away": 1.75,
        }
        for number, odd in [(1, 1.35), (2, 1.45), (3, 1.55)]
    ])
    _, plans = build_multi_play_plans(markets, max_matches=3)
    safe = next(plan for plan in plans if plan.plan_id == "MULTI_PLAY_SAFE")
    value = next(plan for plan in plans if plan.plan_id == "MULTI_PLAY_VALUE")
    assert len({leg.match_number for leg in safe.legs} & {leg.match_number for leg in value.legs}) <= 1
    assert len(value.legs) == 2


def test_strong_anchor_double_is_shadow_only() -> None:
    markets = pd.DataFrame([
        {
            "match_number": "001", "home_team": "Anchor", "away_team": "Away",
            "home_handicap": -1, "spf_odds_home": 1.35, "spf_odds_draw": 5.0,
            "spf_odds_away": 8.0, "rqspf_odds_home": 2.2,
            "rqspf_odds_draw": 3.5, "rqspf_odds_away": 2.6,
        },
        {
            "match_number": "002", "home_team": "Uncertain", "away_team": "Away2",
            "home_handicap": -1, "spf_odds_home": 2.1, "spf_odds_draw": 3.0,
            "spf_odds_away": 3.2, "rqspf_odds_home": 3.2,
            "rqspf_odds_draw": 3.4, "rqspf_odds_away": 1.9,
        },
    ])
    _, plans = build_multi_play_plans(markets, max_matches=2)
    shadow = next(plan for plan in plans if plan.plan_id == "MULTI_PLAY_ANCHOR_DOUBLE_SHADOW")
    assert shadow.is_shadow is True
    assert shadow.total_stake == 4.0
    assert [len(leg.selections) for leg in shadow.legs] == [1, 2]
