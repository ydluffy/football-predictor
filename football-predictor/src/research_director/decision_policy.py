from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UpgradeDecision:
    decision: str
    gate_reasons: list[str]
    details: dict[str, Any]


def decide_candidate_upgrade(
    *,
    current_metrics: dict[str, Any],
    candidate_metrics: dict[str, Any],
    pytest_passed: bool,
    data_quality_ok: bool,
    high_confidence_errors_delta: int,
    brier_improvement_min: float = 0.0,
    cross_season_logloss_difference: float | None = None,
    bootstrap_ci95_high: float | None = None,
    require_cross_season_evidence: bool = False,
) -> UpgradeDecision:
    if not data_quality_ok:
        return UpgradeDecision(decision="keep_current", gate_reasons=["data_quality_failed"], details={})
    if not pytest_passed:
        return UpgradeDecision(decision="keep_current", gate_reasons=["pytest_failed"], details={})
    if high_confidence_errors_delta > 0:
        return UpgradeDecision(
            decision="keep_current",
            gate_reasons=["no_metric_improvement", "high_confidence_errors_increased"],
            details={"delta": int(high_confidence_errors_delta)},
        )

    if require_cross_season_evidence:
        missing = []
        if cross_season_logloss_difference is None:
            missing.append("cross_season_logloss_difference")
        if bootstrap_ci95_high is None:
            missing.append("bootstrap_ci95_high")
        if missing:
            return UpgradeDecision(
                decision="keep_current",
                gate_reasons=["missing_cross_season_evidence"],
                details={"missing": missing},
            )

    if cross_season_logloss_difference is not None and float(cross_season_logloss_difference) >= 0.0:
        return UpgradeDecision(
            decision="keep_current",
            gate_reasons=["cross_season_logloss_not_improved"],
            details={"cross_season_logloss_difference": float(cross_season_logloss_difference)},
        )

    if bootstrap_ci95_high is not None and float(bootstrap_ci95_high) >= 0.0:
        return UpgradeDecision(
            decision="keep_current",
            gate_reasons=["bootstrap_not_significant"],
            details={"bootstrap_ci95_high": float(bootstrap_ci95_high)},
        )

    cur_brier = float(current_metrics.get("brier", 1e9))
    cand_brier = float(candidate_metrics.get("brier", 1e9))
    if cand_brier >= cur_brier - float(brier_improvement_min):
        return UpgradeDecision(
            decision="keep_current",
            gate_reasons=["no_metric_improvement"],
            details={"current_brier": cur_brier, "candidate_brier": cand_brier},
        )

    cur_gap = current_metrics.get("reliability_gap_mean")
    cand_gap = candidate_metrics.get("reliability_gap_mean")
    if cur_gap is not None and cand_gap is not None:
        if float(cand_gap) > float(cur_gap) + 1e-12:
            return UpgradeDecision(
                decision="review_required",
                gate_reasons=["no_metric_improvement", "reliability_gap_worsened"],
                details={"current_gap": float(cur_gap), "candidate_gap": float(cand_gap)},
            )

    return UpgradeDecision(
        decision="promote_candidate",
        gate_reasons=[],
        details={"current_brier": cur_brier, "candidate_brier": cand_brier},
    )
