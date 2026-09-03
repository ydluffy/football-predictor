from __future__ import annotations

from pathlib import Path

import pandas as pd

from world_cup.betting_strategy import build_multi_play_plans


ROOT = Path(__file__).resolve().parents[1]


def _plans(filename: str, max_matches: int):
    markets = pd.read_csv(ROOT / "data" / "manual" / filename).fillna("")
    return build_multi_play_plans(markets, max_matches=max_matches)


def test_august_31_replay_keeps_unmodelled_rqspf_out_of_production() -> None:
    _, plans = _plans("sporttery_handicap_markets_2026-08-31_1807_confirm.csv", 12)
    production = [plan for plan in plans if not plan.is_shadow]
    assert production
    assert all(leg.play_type == "胜平负" for plan in production for leg in plan.legs)
    # The old conversion selected 001 让负; the optimized path keeps that
    # market-only cover opinion out of production.
    assert all(not (leg.match_number == "001" and "让负" in leg.selection_text) for plan in production for leg in plan.legs)


def test_september_1_replay_preserves_strong_spf_and_shadows_uncertain_cover() -> None:
    match_rows, plans = _plans("sporttery_handicap_markets_2026-09-01_2103_confirm_001_010.csv", 10)
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
