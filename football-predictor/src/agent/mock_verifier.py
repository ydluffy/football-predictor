from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent.base import VerifierBase
from agent.schemas import EvidenceBundle, EvidenceItem, MatchContext, VerificationResult


class MockVerifier(VerifierBase):
    def __init__(
        self,
        *,
        line_move_abs_threshold: float = 0.2,
    ) -> None:
        self._line_move_abs_threshold = float(line_move_abs_threshold)

    def collect_evidence(self, match_context: MatchContext) -> EvidenceBundle:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        items: list[EvidenceItem] = [
            EvidenceItem(
                source_type="match_context",
                content="match_context_loaded",
                confidence=0.6,
                timestamp=now,
            )
        ]
        if match_context.line_move is not None:
            items.append(
                EvidenceItem(
                    source_type="market_line_move",
                    content=f"line_move={match_context.line_move}",
                    confidence=0.7,
                    timestamp=now,
                )
            )
        if match_context.injury_flag is not None:
            items.append(
                EvidenceItem(
                    source_type="injury_feed",
                    content=f"injury_flag={match_context.injury_flag}",
                    confidence=0.55,
                    timestamp=now,
                )
            )
        return EvidenceBundle(match=match_context, items=items)

    def verify_local(self, bundle: EvidenceBundle) -> dict[str, Any]:
        mc = bundle.match
        risk_flags: list[str] = []
        conflict_notes: list[str] = []

        if mc.injury_flag == 1:
            risk_flags.append("injury_risk")

        if mc.line_move is not None and abs(float(mc.line_move)) >= self._line_move_abs_threshold:
            risk_flags.append("line_move_risk")

        return {
            "risk_flags": risk_flags,
            "conflict_notes": conflict_notes,
        }

    def verify_global(self, bundle: EvidenceBundle) -> dict[str, Any]:
        mc = bundle.match
        risk_flags: list[str] = []
        conflict_notes: list[str] = []

        odds = [mc.odds_home, mc.odds_draw, mc.odds_away]
        if any(v is None for v in odds):
            risk_flags.append("data_quality_risk")
            conflict_notes.append("missing_odds")
        else:
            o = [float(v) for v in odds if v is not None]
            if any(v <= 1.0 for v in o):
                risk_flags.append("data_quality_risk")
                conflict_notes.append("invalid_odds_value")
            implied_sum = (1.0 / o[0]) + (1.0 / o[1]) + (1.0 / o[2])
            if implied_sum > 1.25 or implied_sum < 0.85:
                risk_flags.append("data_quality_risk")
                conflict_notes.append(f"implied_prob_sum_out_of_range={implied_sum:.3f}")

        return {
            "risk_flags": risk_flags,
            "conflict_notes": conflict_notes,
        }

    def generate_result(
        self,
        *,
        bundle: EvidenceBundle,
        local_result: dict[str, Any],
        global_result: dict[str, Any],
    ) -> VerificationResult:
        risk_flags = sorted(set((local_result.get("risk_flags") or []) + (global_result.get("risk_flags") or [])))
        conflict_notes = (local_result.get("conflict_notes") or []) + (global_result.get("conflict_notes") or [])

        if bundle.items:
            source_confidence = float(sum(i.confidence for i in bundle.items)) / float(len(bundle.items))
        else:
            source_confidence = 0.0

        manual_review_required = bool(risk_flags) or source_confidence < 0.5
        summary = "ok" if not manual_review_required else "risk_detected"
        return VerificationResult(
            match_id=bundle.match.match_id,
            risk_flags=risk_flags,
            source_confidence=source_confidence,
            conflict_notes=[str(x) for x in conflict_notes],
            manual_review_required=manual_review_required,
            summary=summary,
        )

