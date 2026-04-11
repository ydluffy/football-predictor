from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from football_predictor.agents.verifier import RiskFlag


@dataclass(frozen=True, slots=True)
class DecisionResult:
    proba: np.ndarray
    requires_review: bool
    risk_flags: list[RiskFlag]


def apply_risk_adjustment(model_proba: np.ndarray, risk_flags: list[RiskFlag]) -> DecisionResult:
    proba = np.asarray(model_proba, dtype=float)
    if proba.shape != (3,):
        raise ValueError("model_proba must have shape (3,)")

    alpha = min(0.3, 0.1 * len(risk_flags))
    uniform = np.array([1 / 3, 1 / 3, 1 / 3], dtype=float)
    adjusted = (1.0 - alpha) * proba + alpha * uniform
    adjusted = adjusted / adjusted.sum() if adjusted.sum() > 0 else uniform
    requires_review = len(risk_flags) > 0
    return DecisionResult(proba=adjusted, requires_review=requires_review, risk_flags=risk_flags)
