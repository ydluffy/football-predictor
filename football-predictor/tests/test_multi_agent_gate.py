from __future__ import annotations

from multi_agent.gate import RuleGate
from multi_agent.schemas import ActionType, ProposedAction, RiskLevel


def test_rule_gate_blocks_high_risk_by_default():
    gate = RuleGate(allow_high_risk=False)
    action = ProposedAction(action_type=ActionType.run_command, risk_level=RiskLevel.high, description="train_model")
    d = gate.evaluate(action)
    assert d.allowed is False


def test_rule_gate_allows_low_risk():
    gate = RuleGate(allow_high_risk=False)
    action = ProposedAction(action_type=ActionType.write_file, risk_level=RiskLevel.low, description="write_report")
    d = gate.evaluate(action)
    assert d.allowed is True

