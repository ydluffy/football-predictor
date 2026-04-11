from __future__ import annotations

import pandas as pd
import pytest

from config.settings import get_settings
from evaluate.error_analysis import detect_high_confidence_errors, detect_underestimated_draws, export_error_analysis_with_risk


def test_detect_high_confidence_errors_normal_case_writes_file(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3"],
            "league": ["EPL", "EPL", "LaLiga"],
            "p_home": [0.9, 0.81, 0.6],
            "p_draw": [0.05, 0.1, 0.2],
            "p_away": [0.05, 0.09, 0.2],
            "actual": ["D", "H", "A"],
        }
    )
    out = detect_high_confidence_errors(df, prob_threshold=0.8)
    assert settings.eval_high_confidence_errors_path.exists()
    assert {"match_id", "league", "predicted_label", "actual", "max_proba", "p_home", "p_draw", "p_away"} <= set(out.columns)
    assert out["match_id"].tolist() == ["m1"]
    assert out["predicted_label"].tolist() == ["H"]


def test_detect_high_confidence_errors_with_verifier_join_adds_risk_columns(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "league": ["EPL", "EPL"],
            "p_home": [0.9, 0.2],
            "p_draw": [0.05, 0.6],
            "p_away": [0.05, 0.2],
            "actual": ["D", "D"],
        }
    )
    verifier = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "risk_flags": ['["line_move_risk"]', "[]"],
            "manual_review_required": [True, False],
        }
    )
    out = detect_high_confidence_errors(df, prob_threshold=0.8, verifier_results=verifier)
    assert "risk_flags" in out.columns
    assert "manual_review_required" in out.columns
    assert out.loc[0, "risk_flags"] == '["line_move_risk"]'
    assert bool(out.loc[0, "manual_review_required"]) is True


def test_detect_high_confidence_errors_missing_cols_raises(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    df = pd.DataFrame({"p_home": [0.9], "p_draw": [0.05], "actual": ["H"]})
    with pytest.raises(ValueError):
        detect_high_confidence_errors(df)


def test_detect_high_confidence_errors_threshold_behavior(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    df = pd.DataFrame(
        {
            "match_id": ["m1"],
            "p_home": [0.8],
            "p_draw": [0.1],
            "p_away": [0.1],
            "actual": ["D"],
        }
    )
    out = detect_high_confidence_errors(df, prob_threshold=0.8)
    assert len(out) == 1


def test_detect_underestimated_draws_normal_case_writes_file(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3"],
            "league": ["EPL", "EPL", "LaLiga"],
            "p_home": [0.6, 0.2, 0.3],
            "p_draw": [0.1, 0.2, 0.05],
            "p_away": [0.3, 0.6, 0.65],
            "actual": ["D", "D", "H"],
        }
    )
    out = detect_underestimated_draws(df, draw_gap_threshold=0.15)
    assert settings.eval_underestimated_draws_path.exists()
    assert {"match_id", "league", "actual", "p_home", "p_draw", "p_away"} <= set(out.columns)
    assert out["match_id"].tolist() == ["m1"]


def test_detect_underestimated_draws_missing_cols_raises(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    df = pd.DataFrame({"p_home": [0.6], "p_draw": [0.1], "p_away": [0.3]})
    with pytest.raises(ValueError):
        detect_underestimated_draws(df)


def test_export_error_analysis_with_risk_writes_file_with_and_without_verifier(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3"],
            "league": ["EPL", "EPL", "LaLiga"],
            "p_home": [0.9, 0.2, 0.2],
            "p_draw": [0.05, 0.1, 0.05],
            "p_away": [0.05, 0.7, 0.75],
            "actual": ["D", "D", "A"],
        }
    )

    out1 = export_error_analysis_with_risk(df, prob_threshold=0.8, draw_gap_threshold=0.15, verifier_results=None)
    assert settings.eval_error_analysis_with_risk_path.exists()
    assert {"match_id", "error_type", "risk_flags", "manual_review_required"} <= set(out1.columns)

    verifier = pd.DataFrame(
        {
            "match_id": ["m1"],
            "risk_flags": ['["injury_risk"]'],
            "manual_review_required": [True],
        }
    )
    out2 = export_error_analysis_with_risk(df, prob_threshold=0.8, draw_gap_threshold=0.15, verifier_results=verifier)
    assert {"match_id", "error_type", "risk_flags", "manual_review_required"} <= set(out2.columns)
