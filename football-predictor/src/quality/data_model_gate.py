from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


class QualityGateInputError(ValueError):
    """Raised when a quality-gate input cannot produce a trustworthy result."""


@dataclass(frozen=True)
class QualityGateConfig:
    timestamp_column: str
    required_columns: tuple[str, ...]
    odds_columns: tuple[str, ...]
    drift_features: tuple[str, ...]
    max_data_age_hours: float
    max_required_missing_rate: float
    max_column_missing_rate: float
    min_odds_coverage_rate: float
    drift_feature_psi_threshold: float
    max_feature_psi: float
    max_drifted_feature_rate: float
    psi_bins: int
    max_brier: float
    max_reliability_gap: float
    max_calibration_brier_delta: float
    min_calibration_samples: int

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> QualityGateConfig:
        data = raw.get("data", {})
        drift = raw.get("drift", {})
        calibration = raw.get("calibration", {})
        if not isinstance(data, Mapping) or not isinstance(drift, Mapping) or not isinstance(calibration, Mapping):
            raise QualityGateInputError("config sections data, drift and calibration must be objects")
        config = cls(
            timestamp_column=str(data.get("timestamp_column", "date")),
            required_columns=_string_tuple(data.get("required_columns"), "data.required_columns"),
            odds_columns=_string_tuple(data.get("odds_columns"), "data.odds_columns"),
            drift_features=_string_tuple(drift.get("features"), "drift.features"),
            max_data_age_hours=float(data.get("max_data_age_hours", 36.0)),
            max_required_missing_rate=float(data.get("max_required_missing_rate", 0.02)),
            max_column_missing_rate=float(data.get("max_column_missing_rate", 0.05)),
            min_odds_coverage_rate=float(data.get("min_odds_coverage_rate", 0.95)),
            drift_feature_psi_threshold=float(drift.get("feature_psi_threshold", 0.1)),
            max_feature_psi=float(drift.get("max_feature_psi", 0.2)),
            max_drifted_feature_rate=float(drift.get("max_drifted_feature_rate", 0.2)),
            psi_bins=int(drift.get("psi_bins", 10)),
            max_brier=float(calibration.get("max_brier", 0.66)),
            max_reliability_gap=float(calibration.get("max_reliability_gap", 0.15)),
            max_calibration_brier_delta=float(calibration.get("max_brier_delta", 0.01)),
            min_calibration_samples=int(calibration.get("min_samples", 50)),
        )
        config._validate()
        return config

    @classmethod
    def from_json(cls, path: str | Path) -> QualityGateConfig:
        config_path = Path(path)
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise QualityGateInputError(f"cannot load config {config_path}: {exc}") from exc
        if not isinstance(raw, Mapping):
            raise QualityGateInputError("quality-gate config root must be an object")
        return cls.from_mapping(raw)

    def _validate(self) -> None:
        if not self.timestamp_column:
            raise QualityGateInputError("data.timestamp_column cannot be empty")
        if len(self.odds_columns) != 3:
            raise QualityGateInputError("data.odds_columns must contain exactly three columns")
        if self.psi_bins < 2:
            raise QualityGateInputError("drift.psi_bins must be at least 2")
        if self.drift_feature_psi_threshold > self.max_feature_psi:
            raise QualityGateInputError("drift.feature_psi_threshold cannot exceed max_feature_psi")
        if self.min_calibration_samples < 1:
            raise QualityGateInputError("calibration.min_samples must be positive")
        rate_values = {
            "max_required_missing_rate": self.max_required_missing_rate,
            "max_column_missing_rate": self.max_column_missing_rate,
            "min_odds_coverage_rate": self.min_odds_coverage_rate,
            "max_drifted_feature_rate": self.max_drifted_feature_rate,
        }
        for name, value in rate_values.items():
            if not 0.0 <= value <= 1.0:
                raise QualityGateInputError(f"{name} must be between 0 and 1")


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise QualityGateInputError(f"{field} must be a non-empty string array")
    return tuple(value)


def load_metrics(path: str | Path) -> dict[str, Any]:
    metrics_path = Path(path)
    if not metrics_path.is_file():
        raise QualityGateInputError(f"metrics file not found: {metrics_path}")
    try:
        if metrics_path.suffix.lower() == ".json":
            raw = json.loads(metrics_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise QualityGateInputError("metrics JSON root must be an object")
            return raw
        frame = pd.read_csv(metrics_path)
    except (OSError, json.JSONDecodeError, pd.errors.ParserError) as exc:
        raise QualityGateInputError(f"cannot load metrics {metrics_path}: {exc}") from exc
    if frame.empty:
        raise QualityGateInputError(f"metrics file has no rows: {metrics_path}")
    if "run_time" in frame.columns:
        parsed = pd.to_datetime(frame["run_time"], errors="coerce", utc=True)
        valid = parsed.dropna()
        row_index = valid.idxmax() if not valid.empty else frame.index[-1]
    else:
        row_index = frame.index[-1]
    return {str(key): value for key, value in frame.loc[row_index].to_dict().items()}


def _missing_mask(series: pd.Series) -> pd.Series:
    mask = series.isna()
    if pd.api.types.is_object_dtype(series.dtype) or isinstance(series.dtype, pd.StringDtype):
        mask = mask | series.astype("string").str.strip().eq("").fillna(False)
    return mask


def _check(name: str, passed: bool, observed: Any, threshold: Any, details: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "status": "pass" if passed else "fail",
        "observed": observed,
        "threshold": threshold,
    }
    if details is not None:
        payload["details"] = details
    return payload


def _numeric_metric(metrics: Mapping[str, Any], *names: str) -> float:
    for name in names:
        value = metrics.get(name)
        if value is None or pd.isna(value):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            return number
    raise QualityGateInputError(f"metrics missing finite field: {' or '.join(names)}")


def population_stability_index(reference: pd.Series, current: pd.Series, bins: int) -> float:
    reference_values = pd.to_numeric(reference, errors="coerce").dropna().to_numpy(dtype=float)
    current_values = pd.to_numeric(current, errors="coerce").dropna().to_numpy(dtype=float)
    if not len(reference_values) or not len(current_values):
        raise QualityGateInputError("PSI requires non-null numeric values in reference and current data")

    reference_series = pd.Series(reference_values)
    edges = sorted({float(reference_series.quantile(index / bins)) for index in range(bins + 1)})
    if len(edges) < 2:
        value = float(edges[0])
        edges = [value - 1e-9, value + 1e-9]
    edges[0] = -math.inf
    edges[-1] = math.inf
    reference_counts = pd.Series(pd.cut(reference_values, bins=edges, include_lowest=True)).value_counts(sort=False)
    current_counts = pd.Series(pd.cut(current_values, bins=edges, include_lowest=True)).value_counts(sort=False)
    epsilon = 1e-6
    reference_rate = (reference_counts / len(reference_values)).clip(lower=epsilon)
    current_rate = (current_counts / len(current_values)).clip(lower=epsilon)
    ratio = current_rate / reference_rate
    return float(((current_rate - reference_rate) * ratio.map(math.log)).sum())


def evaluate_quality_gate(
    current: pd.DataFrame,
    reference: pd.DataFrame,
    metrics: Mapping[str, Any],
    config: QualityGateConfig,
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    if current.empty:
        raise QualityGateInputError("current dataset has no rows")
    if reference.empty:
        raise QualityGateInputError("reference dataset has no rows")
    as_of_utc = as_of or datetime.now(UTC)
    if as_of_utc.tzinfo is None:
        as_of_utc = as_of_utc.replace(tzinfo=UTC)
    as_of_utc = as_of_utc.astimezone(UTC)

    checks: list[dict[str, Any]] = []
    required_for_data = set(config.required_columns) | {config.timestamp_column} | set(config.odds_columns)
    missing_columns = sorted(required_for_data - set(current.columns))
    if missing_columns:
        raise QualityGateInputError(f"current dataset missing columns: {', '.join(missing_columns)}")

    timestamps = pd.to_datetime(current[config.timestamp_column], errors="coerce", utc=True)
    if timestamps.notna().sum() == 0:
        raise QualityGateInputError(f"column {config.timestamp_column} has no parseable timestamps")
    latest = timestamps.max()
    age_hours = max(0.0, float((as_of_utc - latest.to_pydatetime()).total_seconds() / 3600.0))
    checks.append(
        _check(
            "data_freshness",
            age_hours <= config.max_data_age_hours,
            {"age_hours": round(age_hours, 6), "latest_timestamp": latest.isoformat()},
            {"max_data_age_hours": config.max_data_age_hours},
        )
    )

    missing_rates = {column: float(_missing_mask(current[column]).mean()) for column in config.required_columns}
    overall_missing_rate = float(sum(_missing_mask(current[column]).sum() for column in config.required_columns)) / (
        len(current) * len(config.required_columns)
    )
    max_column_rate = max(missing_rates.values())
    checks.append(
        _check(
            "required_field_missing_rate",
            overall_missing_rate <= config.max_required_missing_rate
            and max_column_rate <= config.max_column_missing_rate,
            {
                "overall_rate": round(overall_missing_rate, 6),
                "max_column_rate": round(max_column_rate, 6),
            },
            {
                "max_required_missing_rate": config.max_required_missing_rate,
                "max_column_missing_rate": config.max_column_missing_rate,
            },
            {"by_column": {key: round(value, 6) for key, value in missing_rates.items()}},
        )
    )

    valid_odds = pd.Series(True, index=current.index)
    for column in config.odds_columns:
        numeric = pd.to_numeric(current[column], errors="coerce")
        valid_odds &= numeric.notna() & numeric.gt(1.0)
    odds_coverage = float(valid_odds.mean())
    checks.append(
        _check(
            "odds_coverage",
            odds_coverage >= config.min_odds_coverage_rate,
            {"coverage_rate": round(odds_coverage, 6), "covered_rows": int(valid_odds.sum()), "rows": len(current)},
            {"min_odds_coverage_rate": config.min_odds_coverage_rate},
        )
    )

    missing_drift_current = sorted(set(config.drift_features) - set(current.columns))
    missing_drift_reference = sorted(set(config.drift_features) - set(reference.columns))
    if missing_drift_current or missing_drift_reference:
        raise QualityGateInputError(
            f"drift columns missing; current={missing_drift_current}, reference={missing_drift_reference}"
        )
    psi_by_feature = {
        feature: population_stability_index(reference[feature], current[feature], config.psi_bins)
        for feature in config.drift_features
    }
    drifted = [name for name, value in psi_by_feature.items() if value > config.drift_feature_psi_threshold]
    max_psi = max(psi_by_feature.values())
    drifted_rate = len(drifted) / len(config.drift_features)
    checks.append(
        _check(
            "feature_drift_psi",
            max_psi <= config.max_feature_psi and drifted_rate <= config.max_drifted_feature_rate,
            {"max_psi": round(max_psi, 6), "drifted_feature_rate": round(drifted_rate, 6)},
            {
                "max_feature_psi": config.max_feature_psi,
                "feature_psi_threshold": config.drift_feature_psi_threshold,
                "max_drifted_feature_rate": config.max_drifted_feature_rate,
            },
            {
                "drifted_features": drifted,
                "psi_by_feature": {key: round(value, 6) for key, value in psi_by_feature.items()},
            },
        )
    )

    brier = _numeric_metric(metrics, "brier_calibrated", "brier")
    reliability_gap = _numeric_metric(metrics, "reliability_gap_mean", "reliability_gap", "ece")
    sample_count = int(_numeric_metric(metrics, "n_samples", "sample_count"))
    brier_raw = _numeric_metric(metrics, "brier_raw", "brier")
    brier_delta = brier - brier_raw
    calibration_passed = (
        brier <= config.max_brier
        and reliability_gap <= config.max_reliability_gap
        and brier_delta <= config.max_calibration_brier_delta
        and sample_count >= config.min_calibration_samples
    )
    checks.append(
        _check(
            "model_calibration",
            calibration_passed,
            {
                "brier": round(brier, 6),
                "reliability_gap": round(reliability_gap, 6),
                "brier_delta": round(brier_delta, 6),
                "sample_count": sample_count,
            },
            {
                "max_brier": config.max_brier,
                "max_reliability_gap": config.max_reliability_gap,
                "max_brier_delta": config.max_calibration_brier_delta,
                "min_samples": config.min_calibration_samples,
            },
        )
    )

    failed = [check["name"] for check in checks if check["status"] == "fail"]
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "as_of_utc": as_of_utc.isoformat(),
        "status": "pass" if not failed else "fail",
        "summary": {"passed": len(checks) - len(failed), "failed": len(failed), "failed_checks": failed},
        "checks": checks,
        "policy": asdict(config),
    }
