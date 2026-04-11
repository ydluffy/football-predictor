from __future__ import annotations

from dataclasses import dataclass

from multi_agent.schemas import ActionType, ProposedAction, RiskLevel


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str


class RuleGate:
    def __init__(self, *, allow_high_risk: bool = False) -> None:
        self._allow_high_risk = bool(allow_high_risk)

    def evaluate(self, action: ProposedAction) -> GateDecision:
        if action.risk_level == RiskLevel.high and not self._allow_high_risk:
            return GateDecision(allowed=False, reason="blocked_high_risk_action")

        if action.action_type in {ActionType.modify_code, ActionType.delete_file}:
            if not self._allow_high_risk:
                return GateDecision(allowed=False, reason="blocked_destructive_action")

        return GateDecision(allowed=True, reason="allowed")

