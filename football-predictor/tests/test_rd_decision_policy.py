from __future__ import annotations

from research_director.decision_policy import decide_candidate_upgrade


def test_decision_policy_blocks_when_brier_not_improved():
    d = decide_candidate_upgrade(
        current_metrics={"brier": 0.2, "reliability_gap_mean": 0.05},
        candidate_metrics={"brier": 0.21, "reliability_gap_mean": 0.04},
        pytest_passed=True,
        data_quality_ok=True,
        high_confidence_errors_delta=0,
    )
    assert d.decision == "keep_current"
    assert "no_metric_improvement" in d.gate_reasons


def test_decision_policy_review_when_reliability_worsened():
    d = decide_candidate_upgrade(
        current_metrics={"brier": 0.2, "reliability_gap_mean": 0.03},
        candidate_metrics={"brier": 0.19, "reliability_gap_mean": 0.06},
        pytest_passed=True,
        data_quality_ok=True,
        high_confidence_errors_delta=0,
    )
    assert d.decision == "review_required"
    assert "no_metric_improvement" in d.gate_reasons
