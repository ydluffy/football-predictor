from __future__ import annotations

import pandas as pd

from world_cup.betting_strategy import build_multi_play_plans


def _market(
    match_number: str,
    home_team: str,
    away_team: str,
    spf: tuple[float, float, float],
    rqspf: tuple[float, float, float],
) -> dict[str, object]:
    return {
        "match_number": match_number,
        "home_team": home_team,
        "away_team": away_team,
        "home_handicap": -1,
        "spf_odds_home": spf[0],
        "spf_odds_draw": spf[1],
        "spf_odds_away": spf[2],
        "rqspf_odds_home": rqspf[0],
        "rqspf_odds_draw": rqspf[1],
        "rqspf_odds_away": rqspf[2],
    }


def test_august_31_replay_keeps_unmodelled_rqspf_out_of_production() -> None:
    markets = pd.DataFrame(
        [
            _market("001", "国际图尔", "库奥皮奥", (2.25, 3.12, 2.74), (5.10, 3.88, 1.48)),
            _market("002", "赫尔火花", "TPS图尔", (1.75, 3.70, 3.48), (3.21, 3.65, 1.84)),
            _market("003", "莱切", "罗马", (7.50, 4.30, 1.31), (2.80, 3.46, 2.07)),
            _market("004", "佐加顿斯", "米亚尔比", (1.35, 4.60, 5.90), (2.10, 3.64, 2.65)),
        ]
    )
    _, plans = build_multi_play_plans(markets, max_matches=12)
    production = [plan for plan in plans if not plan.is_shadow]
    assert production
    assert all(leg.play_type == "胜平负" for plan in production for leg in plan.legs)
    # The old conversion selected 001 让负; the optimized path keeps that
    # market-only cover opinion out of production.
    assert all(not (leg.match_number == "001" and "让负" in leg.selection_text) for plan in production for leg in plan.legs)


def test_september_1_replay_preserves_strong_spf_and_shadows_uncertain_cover() -> None:
    markets = pd.DataFrame(
        [
            _market("001", "利雅新月", "吉达国民", (1.35, 4.60, 5.85), (2.05, 3.80, 2.65)),
            _market("002", "斯旺西", "沃特福德", (1.66, 3.60, 4.02), (3.15, 3.40, 1.93)),
            _market("003", "西汉姆联", "伍尔弗", (1.95, 3.50, 3.02), (3.72, 4.00, 1.64)),
            _market("007", "谢菲联", "博尔顿", (1.46, 3.95, 5.25), (2.45, 3.55, 2.28)),
            _market("010", "都灵", "蒙扎", (1.60, 3.40, 4.75), (3.22, 3.05, 2.04)),
        ]
    )
    match_rows, plans = build_multi_play_plans(markets, max_matches=10)
    production = [plan for plan in plans if not plan.is_shadow]
    production_text = " | ".join(leg.selection_text for plan in production for leg in plan.legs)
    assert "001 利雅新月" in production_text
    assert "007 谢菲联" in production_text
    assert "002 斯旺西" not in production_text
    assert "003 西汉姆联" not in production_text
    tiers = {row["match_number"]: row["candidate_tier"] for row in match_rows}
    assert tiers["001"] == "强胆"
    assert tiers["002"] == "可复式"
    anchor_double = next(plan for plan in plans if plan.plan_id == "MULTI_PLAY_ANCHOR_DOUBLE_SHADOW")
    assert anchor_double.is_shadow is True
    assert "001 利雅新月" in anchor_double.legs[0].selection_text
    assert "002 斯旺西" in anchor_double.legs[1].selection_text
