from __future__ import annotations

import json

import pandas as pd
import pytest

from api import main as api_main
from api.services import research_copilot as copilot
from config.settings import get_settings


@pytest.fixture
def temporary_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(tmp_path))
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


def test_analyze_latest_run_reads_artifacts_and_detects_bias(
    temporary_settings,
) -> None:
    settings = temporary_settings
    settings.artifacts_eval_dir.mkdir(parents=True, exist_ok=True)
    settings.eval_metrics_path.write_text(
        json.dumps({"brier": 0.61, "logloss": 1.2}),
        encoding="utf-8",
    )
    pd.DataFrame(
        {
            "p_home": [0.8, 0.75, 0.7],
            "p_draw": [0.1, 0.15, 0.2],
            "p_away": [0.1, 0.1, 0.1],
            "actual": ["H", "H", "D"],
        }
    ).to_csv(settings.eval_results_path, index=False)

    result = copilot.analyze_latest_run()

    assert result["n_samples"] == 3
    assert result["brier"] == 0.61
    assert result["logloss"] == 1.2
    assert result["distribution"]["pred_label_counts"] == {
        "H": 3,
        "D": 0,
        "A": 0,
    }
    assert "predicted_H_dominant" in result["distribution"]["bias_flags"]
    assert len(result["suggestions"]) == 3


def test_system_status_and_default_artifacts_use_configured_root(
    temporary_settings,
) -> None:
    settings = temporary_settings
    settings.artifacts_research_dir.mkdir(parents=True, exist_ok=True)
    settings.artifacts_eval_dir.mkdir(parents=True, exist_ok=True)
    settings.research_model_registry_path.write_text(
        json.dumps({"current_production_model": {"model_id": "model-7"}}),
        encoding="utf-8",
    )
    settings.research_latest_execution_summary_path.write_text(
        json.dumps({"run_id": "run-7", "decision_result": "promote"}),
        encoding="utf-8",
    )
    settings.eval_metrics_path.write_text(
        json.dumps({"brier": 0.2, "logloss": 0.7}),
        encoding="utf-8",
    )

    status = copilot.show_system_status()
    artifacts = copilot._default_artifacts()

    assert status == {
        "production_model": {"model_id": "model-7"},
        "latest_run_id": "run-7",
        "latest_metrics": {"brier": 0.2, "logloss": 0.7},
        "latest_decision": "promote",
    }
    assert artifacts["metrics_path"] == str(settings.eval_metrics_path)
    assert artifacts["latest_execution_summary_path"] == str(
        settings.research_latest_execution_summary_path
    )


def test_natural_language_router_delegates_without_http_dependencies(
    monkeypatch,
) -> None:
    monkeypatch.setattr(copilot, "_format_today_matches_message", lambda: "schedule")
    monkeypatch.setattr(copilot, "_format_high_brier_message", lambda: "brier")
    monkeypatch.setattr(copilot, "_format_backtest_message", lambda: "backtest")
    monkeypatch.setattr(copilot, "_format_status_message", lambda: "status")

    assert copilot._try_handle_natural_language("今天有什么比赛") == "schedule"
    assert copilot._try_handle_natural_language("解释 brier 为什么高") == "brier"
    assert copilot._try_handle_natural_language("查看回测 ROI") == "backtest"
    assert copilot._try_handle_natural_language("当前模型状态") == "status"
    assert copilot._try_handle_natural_language("") is None


def test_main_preserves_research_copilot_exports() -> None:
    assert api_main.analyze_latest_run is copilot.analyze_latest_run
    assert api_main.run_experiment is copilot.run_experiment
    assert api_main.show_system_status is copilot.show_system_status
