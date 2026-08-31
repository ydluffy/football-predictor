from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from quality.data_model_gate import (
    QualityGateConfig,
    QualityGateInputError,
    evaluate_quality_gate,
    load_metrics,
)

FIXTURES = Path(__file__).parent / "fixtures" / "data_model_quality"
AS_OF = datetime(2026, 8, 27, 0, 0, tzinfo=UTC)


def _config() -> QualityGateConfig:
    return QualityGateConfig.from_json(Path(__file__).parents[1] / "config" / "data_model_quality_gate.json")


def _inputs() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    current = pd.read_csv(FIXTURES / "current.csv")
    reference = pd.read_csv(FIXTURES / "reference.csv")
    metrics = load_metrics(FIXTURES / "metrics.json")
    return current, reference, metrics


def test_quality_gate_passes_complete_fresh_stable_calibrated_data() -> None:
    current, reference, metrics = _inputs()

    report = evaluate_quality_gate(current, reference, metrics, _config(), as_of=AS_OF)

    assert report["status"] == "pass"
    assert report["summary"] == {"passed": 5, "failed": 0, "failed_checks": []}


@pytest.mark.parametrize(
    ("mutation", "failed_check"),
    [
        ("stale", "data_freshness"),
        ("missing", "required_field_missing_rate"),
        ("odds", "odds_coverage"),
        ("drift", "feature_drift_psi"),
        ("calibration", "model_calibration"),
    ],
)
def test_quality_gate_blocks_each_quality_dimension(mutation: str, failed_check: str) -> None:
    current, reference, metrics = _inputs()
    if mutation == "stale":
        current["snapshot_at"] = "2026-08-20T00:00:00Z"
    elif mutation == "missing":
        current.loc[0, "home_team"] = None
    elif mutation == "odds":
        current.loc[0, "odds_home"] = 1.0
    elif mutation == "drift":
        for feature in _config().drift_features:
            current[feature] = pd.to_numeric(current[feature]) + 100.0
    else:
        metrics["brier_calibrated"] = 0.8

    report = evaluate_quality_gate(current, reference, metrics, _config(), as_of=AS_OF)

    assert report["status"] == "fail"
    assert failed_check in report["summary"]["failed_checks"]


def test_quality_gate_rejects_missing_drift_column() -> None:
    current, reference, metrics = _inputs()

    with pytest.raises(QualityGateInputError, match="drift columns missing"):
        evaluate_quality_gate(current.drop(columns=["xg_home"]), reference, metrics, _config(), as_of=AS_OF)


def test_load_metrics_selects_latest_timestamped_csv_row(tmp_path: Path) -> None:
    path = tmp_path / "metrics.csv"
    pd.DataFrame(
        [
            {"run_time": "2026-01-02T00:00:00Z", "brier": 0.4},
            {"run_time": "2026-01-01T00:00:00Z", "brier": 0.9},
        ]
    ).to_csv(path, index=False)

    assert load_metrics(path)["brier"] == pytest.approx(0.4)
