from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product
from math import prod
from pathlib import Path
import re
from typing import Iterable

import pandas as pd

from world_cup.markets import implied_probabilities_from_decimal_odds


BASE_BET_UNIT = 2.0


SPF_LABELS = {
    "home": "主胜",
    "draw": "平",
    "away": "客胜",
}

RQSPF_LABELS = {
    "home": "让胜",
    "draw": "让平",
    "away": "让负",
}


@dataclass(frozen=True)
class StrategyLeg:
    match_number: str
    match_name: str
    play_type: str
    selections: tuple[tuple[str, float], ...]

    @property
    def selection_text(self) -> str:
        choices = "/".join(label for label, _ in self.selections)
        return f"{self.match_number} {self.match_name} {self.play_type}:{choices}"


@dataclass(frozen=True)
class BettingPlan:
    plan_id: str
    plan_type: str
    title: str
    stake: float
    legs: tuple[StrategyLeg, ...]
    rationale: str
    risk_notes: str
    is_shadow: bool = False
    eligibility_note: str = ""

    @property
    def bet_count(self) -> int:
        return int(prod(len(leg.selections) for leg in self.legs))

    @property
    def amount_per_bet(self) -> float:
        if not self.bet_count:
            return 0.0
        multiplier = int(self.stake // (self.bet_count * BASE_BET_UNIT))
        return BASE_BET_UNIT * multiplier if multiplier >= 1 else 0.0

    @property
    def total_stake(self) -> float:
        return self.amount_per_bet * self.bet_count

    @property
    def unused_budget(self) -> float:
        return max(0.0, self.stake - self.total_stake)

    @property
    def multiplier(self) -> int:
        if self.amount_per_bet <= 0:
            return 0
        return int(self.amount_per_bet / BASE_BET_UNIT)

    @property
    def payout_range(self) -> tuple[float, float]:
        payouts = []
        for combination in product(*(leg.selections for leg in self.legs)):
            combined_odds = prod(float(odd) for _, odd in combination)
            payouts.append(self.amount_per_bet * combined_odds)
        if not payouts:
            return 0.0, 0.0
        return min(payouts), max(payouts)

    @property
    def odds_range(self) -> tuple[float, float]:
        odds = []
        for combination in product(*(leg.selections for leg in self.legs)):
            odds.append(prod(float(odd) for _, odd in combination))
        if not odds:
            return 0.0, 0.0
        return min(odds), max(odds)


def _to_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 1.0 else None


def _text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none", "null", "<na>"} else text


def _match_number(value: object) -> str:
    text = _text(value)
    if re.fullmatch(r"\d+(?:\.0+)?", text):
        return str(int(float(text))).zfill(3)
    return text


def _probability(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0.0 <= parsed <= 1.0 else None


def _risk_flags(row: pd.Series) -> set[str]:
    return {flag for flag in _text(row.get("market_risk_flags")).split(",") if flag}


def _is_high_market_risk(row: pd.Series) -> bool:
    return _text(row.get("market_signal_strength")) == "high_risk"


def _is_deeper_than_external(row: pd.Series) -> bool:
    flags = _risk_flags(row)
    return bool({"sporttery_deeper_than_external", "external_shallow_vs_sporttery_deep"} & flags)


def _market_dict(row: pd.Series, prefix: str) -> dict[str, float]:
    return {
        key: odd
        for key, odd in {
            "home": _to_float(row.get(f"{prefix}_odds_home")),
            "draw": _to_float(row.get(f"{prefix}_odds_draw")),
            "away": _to_float(row.get(f"{prefix}_odds_away")),
        }.items()
        if odd is not None
    }


def _ranked_market(odds: dict[str, float]) -> list[tuple[str, float, float]]:
    probabilities = implied_probabilities_from_decimal_odds(odds)
    rows = [
        (key, float(odds[key]), float(probabilities[key] or 0.0))
        for key in odds
    ]
    rows.sort(key=lambda item: (-item[2], item[1]))
    return rows


def _ranked_handicap_market(row: pd.Series, odds: dict[str, float]) -> list[tuple[str, float, float]]:
    usage = _text(row.get("handicap_model_usage"))
    if usage not in {"production_auxiliary", "limited_auxiliary"}:
        return _ranked_market(odds)
    probabilities = {
        key: _probability(row.get(f"handicap_blended_probability_{key}"))
        for key in ("home", "draw", "away")
    }
    if any(value is None for value in probabilities.values()):
        return _ranked_market(odds)
    total = sum(float(value) for value in probabilities.values() if value is not None)
    if total <= 0:
        return _ranked_market(odds)
    ranked = [
        (key, float(odds[key]), float(probabilities[key]) / total)
        for key in odds
    ]
    ranked.sort(key=lambda item: (-item[2], item[1]))
    return ranked


def _has_model_backed_handicap(row: pd.Series) -> bool:
    if _text(row.get("handicap_model_usage")) not in {"production_auxiliary", "limited_auxiliary"}:
        return False
    probabilities = [
        _probability(row.get(f"handicap_blended_probability_{key}"))
        for key in ("home", "draw", "away")
    ]
    return all(value is not None for value in probabilities) and sum(float(value) for value in probabilities) > 0


def _match_name(row: pd.Series) -> str:
    return f"{row.get('home_team', '')} vs {row.get('away_team', '')}".strip()


def _handicap_text(value: object) -> str:
    text = str(value).strip()
    if text and not text.startswith(("+", "-")) and text != "0":
        text = f"{float(text):+g}"
    return text


def classify_match(row: pd.Series) -> dict[str, object]:
    spf = _market_dict(row, "spf")
    rqspf = _market_dict(row, "rqspf")
    spf_rank = _ranked_market(spf)
    rqspf_rank = _ranked_handicap_market(row, rqspf)
    favorite_key, favorite_odds, favorite_probability = spf_rank[0]
    draw_probability = dict((key, probability) for key, _, probability in spf_rank).get("draw", 0.0)
    handicap = _handicap_text(row.get("home_handicap", ""))
    spf_probabilities = {key: probability for key, _, probability in spf_rank}
    rqspf_probabilities = {key: probability for key, _, probability in rqspf_rank}
    handicap_model_backed = _has_model_backed_handicap(row)

    if favorite_probability >= 0.58:
        market_shape = "强热门"
    elif favorite_probability >= 0.47:
        market_shape = "普通热门"
    else:
        market_shape = "均衡盘"
    if draw_probability >= 0.29:
        market_shape = f"{market_shape}/高平局权重"

    if favorite_probability >= 0.58 and favorite_odds <= 1.75 and not _is_high_market_risk(row):
        candidate_tier = "强胆"
    elif favorite_probability >= 0.47 or draw_probability >= 0.29:
        candidate_tier = "可复式"
    else:
        candidate_tier = "仅观察"

    return {
        "match_number": _match_number(row.get("match_number", "")),
        "match_name": _match_name(row),
        "competition": str(row.get("competition", "")),
        "kickoff_time": str(row.get("kickoff_time", "")),
        "handicap": handicap,
        "spf": spf,
        "rqspf": rqspf,
        "spf_rank": spf_rank,
        "rqspf_rank": rqspf_rank,
        "favorite_key": favorite_key,
        "favorite_label": SPF_LABELS[favorite_key],
        "favorite_odds": favorite_odds,
        "favorite_probability": favorite_probability,
        "draw_probability": draw_probability,
        "market_shape": market_shape,
        "candidate_tier": candidate_tier,
        "handicap_probability_source": "model_blended" if handicap_model_backed else "market_implied_only",
        "handicap_production_eligible": handicap_model_backed,
        **{f"spf_probability_{key}": spf_probabilities.get(key, 0.0) for key in ("home", "draw", "away")},
        **{f"rqspf_probability_{key}": rqspf_probabilities.get(key, 0.0) for key in ("home", "draw", "away")},
        "market_signal_strength": _text(row.get("market_signal_strength")),
        "market_risk_flags": _text(row.get("market_risk_flags")),
        "market_signal_note": _text(row.get("market_signal_note")),
        "handicap_model_usage": _text(row.get("handicap_model_usage")),
        "handicap_model_pick": _text(row.get("handicap_model_pick")),
        "handicap_model_edge": row.get("handicap_model_edge", ""),
        "handicap_model_expected_value": row.get("handicap_model_expected_value", ""),
    }


def tactical_play_suggestions(classified: dict[str, object]) -> dict[str, object]:
    favorite = str(classified["favorite_key"])
    draw_probability = float(classified["draw_probability"])
    market_shape = str(classified["market_shape"])
    handicap = str(classified.get("handicap", ""))
    flags = {flag for flag in str(classified.get("market_risk_flags", "")).split(",") if flag}

    if "deep_line_but_under_signal" in flags:
        return {
            "script": "让球偏深但外盘大小球偏小，优先防小胜、不穿盘和 90 分钟胶着。",
            "total_goals": ["1", "2", "3"],
            "correct_scores": ["1:1", "1:0", "0:1", "0:0"],
            "half_full": ["平平", "平胜", "平负"],
        }

    if {"sporttery_deeper_than_external", "external_shallow_vs_sporttery_deep"} & flags:
        if favorite == "home":
            return {
                "script": "体彩让球比外盘更深，主队方向不等于能穿盘，优先防一球小胜和让负/让平。",
                "total_goals": ["2", "3", "1"],
                "correct_scores": ["1:0", "2:1", "1:1", "2:0"],
                "half_full": ["平胜", "平平", "胜胜"],
            }
        if favorite == "away":
            return {
                "script": "体彩让球比外盘更深，客队方向不等于能穿盘，优先防一球小胜和让胜/让平。",
                "total_goals": ["2", "3", "1"],
                "correct_scores": ["0:1", "1:2", "1:1", "0:2"],
                "half_full": ["平负", "平平", "负负"],
            }

    if "均衡盘" in market_shape or draw_probability >= 0.29:
        total_goals = ["1", "2", "3"]
        correct_scores = ["1:1", "1:0", "0:1", "0:0"]
        half_full = ["平平", "平胜", "平负"]
        script = "胶着/防守权重高，优先防 90 分钟平局和低比分。"
    elif favorite == "home":
        total_goals = ["2", "3", "4"] if handicap in {"-1", "-2"} else ["1", "2", "3"]
        correct_scores = ["2:1", "1:0", "2:0", "1:1"]
        half_full = ["平胜", "胜胜", "胜平"]
        script = "主队热门，但优先区分赢球和穿盘，比分集中在小胜/一球差。"
    else:
        total_goals = ["2", "3", "4"] if handicap in {"+1", "+2"} else ["1", "2", "3"]
        correct_scores = ["1:2", "0:1", "0:2", "1:1"]
        half_full = ["平负", "负负", "负平"]
        script = "客队热门，防客队一球小胜或热度过高打不穿。"

    return {
        "script": script,
        "total_goals": total_goals,
        "correct_scores": correct_scores,
        "half_full": half_full,
    }


def _leg_from_rank(
    row: pd.Series,
    *,
    play_type: str,
    rank: list[tuple[str, float, float]],
    labels: dict[str, str],
    count: int = 1,
) -> StrategyLeg:
    choices = tuple((labels[key], odd) for key, odd, _ in rank[:count])
    return StrategyLeg(
        match_number=_match_number(row.get("match_number", "")),
        match_name=_match_name(row),
        play_type=play_type,
        selections=choices,
    )


def _conservative_leg(row: pd.Series, item: dict[str, object]) -> StrategyLeg | None:
    spf_rank = item["spf_rank"]  # type: ignore[assignment]
    rq_rank = item["rqspf_rank"]  # type: ignore[assignment]
    favorite_probability = float(item["favorite_probability"])
    top_spf_key, top_spf_odd, _ = spf_rank[0]  # type: ignore[index]
    top_rq_key, top_rq_odd, _ = rq_rank[0]  # type: ignore[index]

    # Without complete model-backed cover probabilities, an RQSPF price is only
    # a market opinion. It must not silently become a production recommendation.
    if favorite_probability >= 0.52 and top_spf_odd <= 1.85:
        return StrategyLeg(
            match_number=_match_number(row.get("match_number", "")),
            match_name=_match_name(row),
            play_type="胜平负",
            selections=((SPF_LABELS[top_spf_key], float(top_spf_odd)),),
        )
    if _has_model_backed_handicap(row) and not _is_deeper_than_external(row):
        return StrategyLeg(
            match_number=_match_number(row.get("match_number", "")),
            match_name=_match_name(row),
            play_type="让球胜平负",
            selections=((RQSPF_LABELS[top_rq_key], float(top_rq_odd)),),
        )
    return None


def _leg_confidence(leg: StrategyLeg) -> float:
    # Lower odds are not truth, but as a market-derived confidence proxy they
    # are useful for choosing which legs belong in the conservative layer.
    return min(1.0 / odd for _, odd in leg.selections)


def _fixed_odds_legs(
    candidates: list[StrategyLeg],
    *,
    minimum: float,
    maximum: float,
    target: float,
    max_legs: int,
) -> tuple[StrategyLeg, ...]:
    """Pick a unique-match, single-selection combination inside a target odds band."""
    if minimum <= 1.0 or maximum < minimum or not minimum <= target <= maximum:
        raise ValueError("fixed odds require 1 < minimum <= target <= maximum")
    eligible = [leg for leg in candidates if len(leg.selections) == 1]
    ranked: list[tuple[tuple[int, float, float, tuple[str, ...]], tuple[StrategyLeg, ...]]] = []
    for leg_count in range(1, min(max_legs, len(eligible)) + 1):
        for legs in combinations(eligible, leg_count):
            match_numbers = tuple(leg.match_number for leg in legs)
            if len(set(match_numbers)) != leg_count:
                continue
            combined_odds = prod(leg.selections[0][1] for leg in legs)
            if minimum <= combined_odds <= maximum:
                score = (
                    leg_count,
                    abs(combined_odds - target),
                    -min(_leg_confidence(leg) for leg in legs),
                    match_numbers,
                )
                ranked.append((score, legs))
    return min(ranked, key=lambda item: item[0])[1] if ranked else ()


def build_multi_play_plans(
    markets: pd.DataFrame,
    *,
    stake: float = 100.0,
    max_matches: int = 3,
    fixed_odds_min: float = 6.00,
    fixed_odds_max: float = 10.00,
    fixed_odds_target: float = 8.00,
    fixed_odds_max_legs: int = 4,
) -> tuple[list[dict[str, object]], list[BettingPlan]]:
    if markets.empty:
        return [], []

    usable_rows = []
    for _, row in markets.iterrows():
        if _market_dict(row, "spf") and _market_dict(row, "rqspf"):
            usable_rows.append(row)
    if not usable_rows:
        return [], []
    frame = pd.DataFrame(usable_rows).head(max_matches)
    classified = [classify_match(row) for _, row in frame.iterrows()]
    suggestions = [tactical_play_suggestions(item) for item in classified]

    conservative_candidates: list[tuple[StrategyLeg, bool]] = []
    shadow_single_candidates: list[StrategyLeg] = []
    hedge_legs: list[StrategyLeg] = []
    high_legs: list[StrategyLeg] = []

    for (_, row), item in zip(frame.iterrows(), classified):
        rq_rank = item["rqspf_rank"]  # type: ignore[assignment]
        spf_rank = item["spf_rank"]  # type: ignore[assignment]
        production_leg = _conservative_leg(row, item)
        if production_leg is not None:
            conservative_candidates.append((production_leg, _is_high_market_risk(row)))
        shadow_single_candidates.append(
            _leg_from_rank(row, play_type="胜平负", rank=spf_rank, labels=SPF_LABELS, count=1)  # type: ignore[arg-type]
        )
        hedge_legs.append(
            _leg_from_rank(row, play_type="胜平负", rank=spf_rank, labels=SPF_LABELS, count=2)  # type: ignore[arg-type]
        )
        # Let-draw is often the best high-payout expression of "favorite wins by one"
        # or "underdog loses by one" scripts.
        rq_by_key = {key: (key, odd, prob) for key, odd, prob in rq_rank}  # type: ignore[union-attr]
        high_choice = [rq_by_key.get("draw") or rq_rank[0]]  # type: ignore[index]
        high_legs.append(
            _leg_from_rank(row, play_type="让球胜平负", rank=high_choice, labels=RQSPF_LABELS, count=1)  # type: ignore[arg-type]
        )

    low_risk_candidates = [leg for leg, high_risk in conservative_candidates if not high_risk]
    conservative_pool = low_risk_candidates
    conservative_legs = sorted(conservative_pool, key=_leg_confidence, reverse=True)[:2]
    ranked_production = sorted(conservative_pool, key=_leg_confidence, reverse=True)
    # Keep at most one shared core leg between safe and value. With three valid
    # candidates this yields safe=[1,2], value=[2,3], instead of two duplicates.
    value_pool = [leg for leg in ranked_production if not conservative_legs or leg.match_number != conservative_legs[0].match_number]
    value_legs = value_pool[:2]
    fixed_odds_legs = _fixed_odds_legs(
        shadow_single_candidates,
        minimum=fixed_odds_min,
        maximum=fixed_odds_max,
        target=fixed_odds_target,
        max_legs=fixed_odds_max_legs,
    )

    signal_notes = [
        str(item.get("market_signal_note", ""))
        for item in classified
        if item.get("market_signal_note")
    ]
    risk_suffix = "；".join(signal_notes[:3]) if signal_notes else "无额外盘口信号。"

    plans: list[BettingPlan] = []
    if len(conservative_legs) >= 2:
        plans.append(BettingPlan(
            plan_id="MULTI_PLAY_SAFE",
            plan_type="稳健",
            title="稳健方案：最多两场低风险方向",
            stake=stake,
            legs=tuple(conservative_legs),
            rationale="稳健层优先减少串关断腿，只选择市场置信度最高的两个方向。",
            risk_notes=f"仍是串关，不等于保本；若赛前有伤停或盘口跳变，应改为单场观察。盘口信号：{risk_suffix}",
            eligibility_note="仅含非高风险且通过生产资格闸门的方向。",
        ))
    if len(value_legs) >= 2:
        plans.append(BettingPlan(
            plan_id="MULTI_PLAY_VALUE",
            plan_type="价值",
            title="价值方案：两场方向串关",
            stake=stake,
            legs=tuple(value_legs),
            rationale="只保留两个通过生产资格闸门的方向，并限制与稳健方案最多共享一个核心场次。",
            risk_notes=f"这是收益弹性方案，不应和稳健方案混为一谈。高风险内外盘分歧场已优先降权。盘口信号：{risk_suffix}",
            eligibility_note="两腿制；与稳健方案最多共享一场。",
        ))
    hedge_selected = tuple(hedge_legs[:2])
    hedge_plan = BettingPlan(
            plan_id="MULTI_PLAY_HEDGE",
            plan_type="防冷",
            title="防冷方案：胜平负双选覆盖冷门分支",
            stake=BASE_BET_UNIT * int(prod(len(leg.selections) for leg in hedge_selected)),
            legs=hedge_selected,
            rationale="每场选市场概率最高的两个胜平负结果，用注数换覆盖率。",
            risk_notes=f"双选会摊薄单注金额，命中后返奖区间取决于具体赛果。盘口信号：{risk_suffix}",
            is_shadow=True,
            eligibility_note="影子验证，不进入真实或正式模拟投注台账。",
        )
    plans.append(hedge_plan)
    high_selected = tuple(high_legs[:3])
    high_plan = BettingPlan(
            plan_id="MULTI_PLAY_HIGH",
            plan_type="博高",
            title="博高方案：让平脚本",
            stake=BASE_BET_UNIT * int(prod(len(leg.selections) for leg in high_selected)),
            legs=high_selected,
            rationale="让平对应一球差/刚好打到盘口，是比分和让球之间最适合博高倍的中间玩法。",
            risk_notes=f"让平天然波动大，只适合小额观察，不宜作为主仓位。盘口信号：{risk_suffix}",
            is_shadow=True,
            eligibility_note="影子验证，不进入真实或正式模拟投注台账。",
        )
    plans.append(high_plan)

    anchors = [
        (row, item) for (_, row), item in zip(frame.iterrows(), classified)
        if item["candidate_tier"] == "强胆"
    ]
    doubles = [
        (row, item) for (_, row), item in zip(frame.iterrows(), classified)
        if item["candidate_tier"] == "可复式"
    ]
    if anchors and doubles:
        anchor_row, anchor_item = anchors[0]
        double_row, double_item = doubles[0]
        if _match_number(anchor_row.get("match_number", "")) != _match_number(double_row.get("match_number", "")):
            anchor_double_legs = (
                _leg_from_rank(anchor_row, play_type="胜平负", rank=anchor_item["spf_rank"], labels=SPF_LABELS, count=1),  # type: ignore[arg-type]
                _leg_from_rank(double_row, play_type="胜平负", rank=double_item["spf_rank"], labels=SPF_LABELS, count=2),  # type: ignore[arg-type]
            )
            plans.append(BettingPlan(
                plan_id="MULTI_PLAY_ANCHOR_DOUBLE_SHADOW",
                plan_type="强胆复式观察",
                title="强胆 + 不确定场双选影子方案",
                stake=BASE_BET_UNIT * 2,
                legs=anchor_double_legs,
                rationale="复刻中奖彩票中可学习的结构：一个强方向作锚点，另一场用双选覆盖不确定性。",
                risk_notes="仅用于检验结构，不证明上传样本具有可复制收益；严禁因锚点重复而叠加真实投入。",
                is_shadow=True,
                eligibility_note="影子验证，至少积累完整胜负样本后再评估。",
            ))
    if fixed_odds_legs:
        plans.append(
            BettingPlan(
                plan_id="MULTI_PLAY_FIXED_ODDS_SHADOW",
                plan_type="固定赔率观察",
                title=f"固定赔率影子方案：目标 {fixed_odds_target:.2f}",
                stake=BASE_BET_UNIT,
                legs=fixed_odds_legs,
                rationale=(
                    f"从低风险方向中选择总赔率位于 {fixed_odds_min:.2f}–{fixed_odds_max:.2f} 的组合，"
                    f"先减少串关腿数，再选择最接近 {fixed_odds_target:.2f} 的方案，用于持续检验固定赔率带命中率。"
                ),
                risk_notes=(
                    "仅作影子观察，不得自动写入真实投注台账或增加投注金额；"
                    f"若没有落在 {fixed_odds_min:.2f}–{fixed_odds_max:.2f} 的合格组合，本方案应为空。"
                ),
                is_shadow=True,
                eligibility_note="影子验证，不进入真实或正式模拟投注台账。",
            )
        )

    match_rows = []
    for item, suggestion in zip(classified, suggestions):
        match_rows.append(
            {
                **{
                    key: item[key]
                    for key in [
                        "match_number",
                        "match_name",
                        "competition",
                        "kickoff_time",
                        "handicap",
                        "favorite_label",
                        "favorite_odds",
                        "favorite_probability",
                        "draw_probability",
                        "market_shape",
                        "candidate_tier",
                        "handicap_probability_source",
                        "handicap_production_eligible",
                        "spf_probability_home",
                        "spf_probability_draw",
                        "spf_probability_away",
                        "rqspf_probability_home",
                        "rqspf_probability_draw",
                        "rqspf_probability_away",
                        "market_signal_strength",
                        "market_risk_flags",
                        "market_signal_note",
                        "handicap_model_usage",
                        "handicap_model_pick",
                        "handicap_model_edge",
                        "handicap_model_expected_value",
                    ]
                },
                "script": suggestion["script"],
                "total_goals_suggestion": "/".join(suggestion["total_goals"]),
                "correct_score_suggestion": "/".join(suggestion["correct_scores"]),
                "half_full_suggestion": "/".join(suggestion["half_full"]),
            }
        )
    return match_rows, plans


def plans_to_frame(plans: Iterable[BettingPlan]) -> pd.DataFrame:
    rows = []
    for plan in plans:
        min_odds, max_odds = plan.odds_range
        min_payout, max_payout = plan.payout_range
        rows.append(
            {
                "plan_id": plan.plan_id,
                "plan_type": plan.plan_type,
                "title": plan.title,
                "stake": round(plan.stake, 2),
                "bet_count": plan.bet_count,
                "base_bet_unit": round(BASE_BET_UNIT, 2),
                "multiplier": plan.multiplier,
                "amount_per_bet": round(plan.amount_per_bet, 2),
                "total_stake": round(plan.total_stake, 2),
                "unused_budget": round(plan.unused_budget, 2),
                "estimated_odds_min": round(min_odds, 4),
                "estimated_odds_max": round(max_odds, 4),
                "estimated_payout_min": round(min_payout, 2),
                "estimated_payout_max": round(max_payout, 2),
                "estimated_net_min": round(min_payout - plan.total_stake, 2),
                "estimated_net_max": round(max_payout - plan.total_stake, 2),
                "selections": " + ".join(leg.selection_text for leg in plan.legs),
                "rationale": plan.rationale,
                "risk_notes": plan.risk_notes,
                "is_shadow": plan.is_shadow,
                "eligibility_note": plan.eligibility_note,
            }
        )
    return pd.DataFrame(rows)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return ""
    headers = [str(column) for column in frame.columns]
    rows = [
        [str(value) for value in row]
        for row in frame.astype(object).itertuples(index=False, name=None)
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell.replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)


def write_multi_play_report(
    *,
    match_rows: list[dict[str, object]],
    plans: list[BettingPlan],
    output_path: str | Path,
    title: str,
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    plan_frame = plans_to_frame(plans)
    match_frame = pd.DataFrame(match_rows)
    shadow_frame = plan_frame[plan_frame["is_shadow"].astype(bool)].copy() if not plan_frame.empty else plan_frame
    production_frame = plan_frame[~plan_frame["is_shadow"].astype(bool)].copy() if not plan_frame.empty else plan_frame

    lines = [
        f"# {title}",
        "",
        "说明：本报告把体彩玩法拆成“稳健、防冷、博高”三层。当前若未接入总进球、比分、半全场官方赔率，相关玩法只作为方向候选，不计入模拟收益账本。",
        "",
        "## 场次脚本",
        "",
    ]
    if match_frame.empty:
        lines.append("暂无可分析场次。")
    else:
        lines.append(
            _markdown_table(
                match_frame[
                    [
                        "match_number",
                        "competition",
                        "kickoff_time",
                        "match_name",
                        "handicap",
                        "market_shape",
                        "candidate_tier",
                        "handicap_probability_source",
                        "handicap_production_eligible",
                        "market_signal_strength",
                        "market_risk_flags",
                        "market_signal_note",
                        "handicap_model_usage",
                        "handicap_model_pick",
                        "handicap_model_edge",
                        "total_goals_suggestion",
                        "correct_score_suggestion",
                        "half_full_suggestion",
                    ]
                ]
            )
        )
    lines.extend(["", "## 生产投注候选（是否入账以终版闸门为准）", ""])
    if production_frame.empty:
        lines.append("暂无生产投注候选。")
    else:
        lines.append(
            _markdown_table(
                production_frame[
                    [
                        "plan_type",
                        "title",
                        "stake",
                        "bet_count",
                        "multiplier",
                        "amount_per_bet",
                        "total_stake",
                        "unused_budget",
                        "estimated_payout_min",
                        "estimated_payout_max",
                        "estimated_net_min",
                        "estimated_net_max",
                        "selections",
                    ]
                ]
            )
        )
    lines.extend(["", "## 影子方案（全部不入账）", ""])
    if shadow_frame.empty:
        lines.append("本次没有合格影子方案。")
    else:
        lines.append("以下按每个组合2元虚拟观察，用于统计命中率、ROI和最大回撤，不得复制到真实投注台账。")
        lines.append("")
        lines.append(
            _markdown_table(
                shadow_frame[
                    [
                        "title",
                        "total_stake",
                        "estimated_odds_min",
                        "estimated_payout_min",
                        "selections",
                        "risk_notes",
                    ]
                ]
            )
        )
    lines.extend(
        [
            "",
            "## 使用原则",
            "",
            "- 稳健层优先控制断腿风险，适合进入模拟账本。",
            "- 防冷层用多选覆盖爆冷或平局，重点观察是否能减少大热误判。",
            "- 博高层只适合小额，核心看让平、比分、半全场是否与比赛脚本一致。",
            "- 固定赔率影子层必须在每次用户回复中单独展示，即使没有方案也要说明原因；它不属于真实入账方案。",
            "- 所有复盘必须按体彩 90 分钟口径结算，加时和点球只做晋级分析。",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
