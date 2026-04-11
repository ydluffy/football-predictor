from __future__ import annotations

import math

import numpy as np
import pandas as pd

from verifier.interface import VerifierCheck, VerifierReport


class SimpleVerifier:
    def __init__(self, *, proba_tol: float = 1e-3) -> None:
        self._proba_tol = float(proba_tol)

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
    ) -> VerifierReport:
        checks: list[VerifierCheck] = []

        required_cols = {"p_home", "p_draw", "p_away", "actual", "model_type"}
        missing = sorted(required_cols - set(results.columns))
        checks.append(
            VerifierCheck(
                name="results_schema",
                passed=len(missing) == 0,
                details="ok" if not missing else f"missing={missing}",
            )
        )

        p = results[["p_home", "p_draw", "p_away"]].to_numpy(dtype=float, copy=False)
        finite = bool(np.isfinite(p).all())
        row_sum = p.sum(axis=1)
        sum_ok = bool(np.allclose(row_sum, 1.0, atol=self._proba_tol))
        checks.append(
            VerifierCheck(
                name="proba_sum_to_one",
                passed=finite and sum_ok,
                details="ok" if finite and sum_ok else "non_finite_or_sum_mismatch",
            )
        )

        brier = float(metrics.get("brier", float("nan")))
        logloss = float(metrics.get("logloss", float("nan")))
        checks.append(
            VerifierCheck(
                name="metrics_finite",
                passed=math.isfinite(brier) and math.isfinite(logloss),
                details=f"brier={brier} logloss={logloss}",
            )
        )

        rg = float(reliability_gap_mean)
        checks.append(
            VerifierCheck(
                name="reliability_gap_mean_finite",
                passed=math.isfinite(rg),
                details=f"reliability_gap_mean={rg}",
            )
        )

        has_league = "league" in results.columns
        checks.append(
            VerifierCheck(
                name="league_metrics_consistency",
                passed=(not has_league and league_metrics is None) or (has_league and league_metrics is not None),
                details="ok" if (not has_league and league_metrics is None) or (has_league and league_metrics is not None) else "league_metrics_missing_or_unexpected",
            )
        )

        passed = all(c.passed for c in checks)
        return VerifierReport(
            run_time=run_time,
            model_type=model_type,
            feature_version=feature_version,
            calibration_method=calibration_method,
            n_samples=int(len(results)),
            passed=passed,
            checks=checks,
        )
