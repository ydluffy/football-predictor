from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "optimize_betting_portfolio.py"
SPEC = importlib.util.spec_from_file_location("optimize_betting_portfolio", MODULE_PATH)
optimizer = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(optimizer)


def test_expected_value_and_kelly_only_select_positive_edges():
    candidates = pd.DataFrame(
        [
            {
                "candidate_id": "good",
                "match_key": "M1",
                "play_type": "spf",
                "selection": "home",
                "odds": 2.00,
                "model_prob": 0.62,
                "risk_score": 0.0,
            },
            {
                "candidate_id": "bad",
                "match_key": "M2",
                "play_type": "spf",
                "selection": "away",
                "odds": 1.80,
                "model_prob": 0.45,
                "risk_score": 0.0,
            },
        ]
    )

    frame = optimizer.optimize_candidates(candidates, budget=100, risk_aversion=0)

    assert frame["candidate_id"].tolist() == ["good"]
    assert frame.loc[0, "edge"] == 0.24
    assert frame.loc[0, "suggested_stake"] % 2 == 0
    assert frame.loc[0, "suggested_stake"] <= 100


def test_optimizer_respects_match_budget_cap():
    candidates = pd.DataFrame(
        [
            {"candidate_id": "a", "match_key": "M1", "odds": 3.0, "model_prob": 0.55},
            {"candidate_id": "b", "match_key": "M1", "odds": 2.5, "model_prob": 0.58},
            {"candidate_id": "c", "match_key": "M2", "odds": 2.2, "model_prob": 0.60},
        ]
    )

    frame = optimizer.optimize_candidates(candidates, budget=100, risk_aversion=0, max_per_match=20)

    assert frame.groupby("match_key")["suggested_stake"].sum().max() <= 20
    assert frame["suggested_stake"].sum() <= 100


def test_implied_probability_fallback_keeps_no_edge_out():
    candidates = pd.DataFrame(
        [{"candidate_id": "market_only", "match_key": "M1", "odds": 2.0, "play_type": "total_goals"}]
    )

    frame = optimizer.optimize_candidates(candidates, budget=100)

    assert frame.empty


def test_optimizer_can_derive_effective_odds_from_plan_candidate():
    candidates = pd.DataFrame(
        [
            {
                "title": "total goals 2/3",
                "play_type": "total_goals",
                "selections": "2@3.7 / 3@3.3",
                "total_stake": 100,
                "estimated_payout_min": 165,
                "model_edge": 0.12,
                "confidence": 0.70,
            }
        ]
    )

    frame = optimizer.optimize_candidates(candidates, budget=100, risk_aversion=0)

    assert frame.loc[0, "candidate_id"] == "total goals 2/3"
    assert frame.loc[0, "odds"] == 1.65
    assert frame.loc[0, "suggested_stake"] > 0
