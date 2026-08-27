from __future__ import annotations

import pandas as pd

from strategy.shadow_portfolio_v2 import ShadowPortfolioPolicy, build_shadow_portfolio


def test_shadow_portfolio_rejects_market_only_long_and_high_odds_candidates():
    candidates = pd.DataFrame(
        [
            {"candidate_id": "market", "gate_status": "eligible", "probability_source": "market_only", "odds": 2.0, "model_prob": 0.7, "leg_count": 1, "match_key": "M1"},
            {"candidate_id": "long", "gate_status": "eligible", "probability_source": "shadow_v2", "odds": 3.0, "model_prob": 0.6, "leg_count": 3, "match_keys": "M2,M3,M4"},
            {"candidate_id": "high", "gate_status": "eligible", "probability_source": "shadow_v2", "odds": 8.0, "model_prob": 0.3, "leg_count": 1, "match_key": "M5"},
        ]
    )
    portfolio, audit = build_shadow_portfolio(candidates)
    assert portfolio.empty
    assert audit["rejection_counts"] == {
        "no_independent_model_probability": 1,
        "too_many_legs": 1,
        "odds_outside_policy": 1,
    }


def test_shadow_portfolio_applies_haircut_and_exposure_caps():
    candidates = pd.DataFrame(
        [
            {"candidate_id": "a", "gate_status": "shadow_eligible", "probability_source": "shadow_v2", "odds": 2.0, "model_prob": 0.64, "uncertainty": 0.02, "leg_count": 1, "match_key": "M1", "competition": "E0"},
            {"candidate_id": "b", "gate_status": "eligible", "probability_source": "shadow_v2", "odds": 2.2, "model_prob": 0.62, "uncertainty": 0.02, "leg_count": 1, "match_key": "M1", "competition": "E0"},
            {"candidate_id": "c", "gate_status": "eligible", "probability_source": "shadow_v2", "odds": 2.0, "model_prob": 0.63, "uncertainty": 0.02, "leg_count": 1, "match_key": "M2", "competition": "SP1"},
        ]
    )
    policy = ShadowPortfolioPolicy(budget=100, max_match_exposure_fraction=0.12)
    portfolio, audit = build_shadow_portfolio(candidates, policy)
    assert not portfolio.empty
    assert portfolio["mode"].eq("shadow_only").all()
    assert max(audit["match_exposure"].values()) <= 12.0
    assert audit["total_stake"] <= 50.0
    assert audit["production_change_performed"] is False
