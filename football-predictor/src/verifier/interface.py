from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd


@dataclass(frozen=True)
class VerifierCheck:
    name: str
    passed: bool
    details: str


@dataclass(frozen=True)
class VerifierReport:
    run_time: str
    model_type: str
    feature_version: str
    calibration_method: str
    n_samples: int
    passed: bool
    checks: list[VerifierCheck]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_time": self.run_time,
            "model_type": self.model_type,
            "feature_version": self.feature_version,
            "calibration_method": self.calibration_method,
            "n_samples": int(self.n_samples),
            "passed": bool(self.passed),
            "checks": [{"name": c.name, "passed": bool(c.passed), "details": c.details} for c in self.checks],
        }


class Verifier(Protocol):
    def verify(
        self,
        *,
        run_time: str,
        model_type: str,
        feature_version: str,
        calibration_method: str,
        results: pd.DataFrame,
        metrics: dict[str, float],
        reliability_gap_mean: float,
        league_metrics: pd.DataFrame | None,
    ) -> VerifierReport: ...
