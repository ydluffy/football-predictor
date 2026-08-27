from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ShadowPortfolioPolicy:
    budget: float = 100.0
    unit: float = 2.0
    min_edge: float = 0.025
    probability_haircut: float = 0.02
    max_decimal_odds: float = 4.0
    max_legs: int = 2
    max_total_stake_fraction: float = 0.50
    max_candidate_stake_fraction: float = 0.15
    max_match_exposure_fraction: float = 0.20
    max_competition_exposure_fraction: float = 0.30
    fractional_kelly: float = 0.15


def _number(value: object, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _keys(value: object) -> tuple[str, ...]:
    text = _text(value)
    if not text:
        return ()
    return tuple(sorted({part.strip() for part in text.replace("+", ",").split(",") if part.strip()}))


def _round_down(value: float, unit: float) -> float:
    return float(np.floor(max(0.0, value) / unit) * unit)


def build_shadow_portfolio(
    candidates: pd.DataFrame,
    policy: ShadowPortfolioPolicy = ShadowPortfolioPolicy(),
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Create a conservative shadow-only portfolio from provenance-safe probabilities."""
    rejection_counts: dict[str, int] = {}
    prepared: list[dict[str, Any]] = []

    def reject(reason: str) -> None:
        rejection_counts[reason] = rejection_counts.get(reason, 0) + 1

    for index, row in candidates.fillna("").iterrows():
        gate = _text(row.get("gate_status")).lower()
        source = _text(row.get("probability_source")).lower()
        odds = _number(row.get("odds"))
        model_prob = _number(row.get("model_prob"), -1.0)
        uncertainty = max(0.0, _number(row.get("uncertainty"), policy.probability_haircut))
        leg_count = int(_number(row.get("leg_count"), 1.0))
        match_keys = _keys(row.get("match_keys")) or _keys(row.get("match_key"))
        if gate not in {"eligible", "shadow_eligible"}:
            reject("gate_not_eligible")
            continue
        if source in {"", "market", "market_only", "implied_odds"}:
            reject("no_independent_model_probability")
            continue
        if model_prob <= 0.0 or model_prob >= 1.0:
            reject("invalid_model_probability")
            continue
        if odds <= 1.0 or odds > policy.max_decimal_odds:
            reject("odds_outside_policy")
            continue
        if leg_count < 1 or leg_count > policy.max_legs:
            reject("too_many_legs")
            continue
        if not match_keys or len(match_keys) != leg_count:
            reject("match_key_mismatch")
            continue
        conservative_prob = max(0.0, model_prob - uncertainty)
        edge = conservative_prob * odds - 1.0
        if edge < policy.min_edge:
            reject("edge_below_haircut_threshold")
            continue
        full_kelly = edge / (odds - 1.0)
        score = edge / max(1.0, np.sqrt(leg_count) * odds)
        prepared.append(
            {
                "candidate_id": _text(row.get("candidate_id")) or f"S{index + 1}",
                "competition": _text(row.get("competition")) or "UNKNOWN",
                "match_keys": ",".join(match_keys),
                "leg_count": leg_count,
                "selection": _text(row.get("selection")) or _text(row.get("selections")),
                "odds": odds,
                "model_prob": model_prob,
                "uncertainty": uncertainty,
                "conservative_prob": conservative_prob,
                "conservative_edge": edge,
                "risk_adjusted_score": score,
                "kelly_fraction": min(policy.max_candidate_stake_fraction, full_kelly * policy.fractional_kelly),
                "probability_source": source,
                "mode": "shadow_only",
            }
        )

    ranked = pd.DataFrame(prepared)
    if ranked.empty:
        return ranked, {
            "mode": "shadow_only",
            "input_rows": int(len(candidates)),
            "eligible_rows": 0,
            "selected_rows": 0,
            "rejection_counts": rejection_counts,
            "total_stake": 0.0,
            "production_change_performed": False,
        }

    ranked = ranked.sort_values(
        ["risk_adjusted_score", "conservative_edge", "odds"],
        ascending=[False, False, True],
        kind="mergesort",
    )
    total_cap = policy.budget * policy.max_total_stake_fraction
    candidate_cap = policy.budget * policy.max_candidate_stake_fraction
    match_cap = policy.budget * policy.max_match_exposure_fraction
    competition_cap = policy.budget * policy.max_competition_exposure_fraction
    match_used: dict[str, float] = {}
    competition_used: dict[str, float] = {}
    total_used = 0.0
    selected: list[dict[str, Any]] = []
    for row in ranked.to_dict(orient="records"):
        match_keys = tuple(row["match_keys"].split(","))
        room = [total_cap - total_used, candidate_cap, competition_cap - competition_used.get(row["competition"], 0.0)]
        room.extend(match_cap - match_used.get(key, 0.0) for key in match_keys)
        desired = max(policy.unit, policy.budget * float(row["kelly_fraction"]))
        stake = _round_down(min([desired, *room]), policy.unit)
        if stake < policy.unit:
            reject("exposure_cap")
            continue
        row["shadow_stake"] = stake
        row["expected_profit"] = round(stake * float(row["conservative_edge"]), 2)
        row["estimated_payout"] = round(stake * float(row["odds"]), 2)
        selected.append(row)
        total_used += stake
        competition_used[row["competition"]] = competition_used.get(row["competition"], 0.0) + stake
        for key in match_keys:
            match_used[key] = match_used.get(key, 0.0) + stake

    result = pd.DataFrame(selected)
    audit = {
        "mode": "shadow_only",
        "input_rows": int(len(candidates)),
        "eligible_rows": int(len(ranked)),
        "selected_rows": int(len(result)),
        "rejection_counts": rejection_counts,
        "total_stake": round(total_used, 2),
        "unused_budget": round(policy.budget - total_used, 2),
        "max_total_stake": round(total_cap, 2),
        "match_exposure": {key: round(value, 2) for key, value in sorted(match_used.items())},
        "competition_exposure": {key: round(value, 2) for key, value in sorted(competition_used.items())},
        "policy": policy.__dict__,
        "production_change_performed": False,
    }
    return result.reset_index(drop=True), audit
