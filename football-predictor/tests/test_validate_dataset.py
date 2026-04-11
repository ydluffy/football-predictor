from __future__ import annotations

import json

import pandas as pd
import pytest

from config.settings import get_settings
from data.mock_data_generator import generate_mock_matches
from data.validate_dataset import build_missing_report, ensure_match_id, validate_matches_dataset


def test_build_missing_report_fields_exist_and_ratios():
    df = pd.DataFrame({"a": [1, 0, None], "b": ["x", None, "y"]})
    rep = build_missing_report(df)
    assert {"field", "exists", "non_null_ratio", "non_zero_ratio"} <= set(rep.columns)
    assert bool(rep.loc[rep["field"] == "a", "exists"].iloc[0]) is True


def test_validate_matches_dataset_writes_outputs(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    df = generate_mock_matches(n_rows=50, feature_version="v3")
    payload = validate_matches_dataset(df, "v3")
    assert settings.eval_dataset_validation_path.exists()
    assert settings.eval_dataset_missing_report_path.exists()
    assert payload["row_count"] == 50
    assert payload["required_fields_missing"] == []
    assert 0.0 <= payload["parseable_date_ratio"] <= 1.0

    loaded = json.loads(settings.eval_dataset_validation_path.read_text(encoding="utf-8"))
    assert loaded["feature_version"] == "v3"


def test_validate_matches_dataset_missing_required_fields_reported(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    df = pd.DataFrame({"match_id": ["m1"], "odds_home": [2.0], "odds_draw": [3.0], "actual_result": ["H"]})
    payload = validate_matches_dataset(df, "v1")
    assert "odds_away" in payload["required_fields_missing"]


def test_validate_matches_dataset_invalid_feature_version_raises():
    df = pd.DataFrame({"match_id": ["m1"], "odds_home": [2.0], "odds_draw": [3.0], "odds_away": [4.0], "actual_result": ["H"]})
    with pytest.raises(ValueError):
        validate_matches_dataset(df, "bad")


def test_validate_matches_dataset_autogenerates_match_id_when_missing(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    df = pd.DataFrame(
        {
            "date": ["2025-08-15", "2025-08-16"],
            "league": ["E0", "E0"],
            "home_team": ["Man United", "Arsenal"],
            "away_team": ["Fulham", "Chelsea"],
            "odds_home": [1.6, 1.8],
            "odds_draw": [4.2, 3.9],
            "odds_away": [5.2, 4.1],
            "actual_result": ["H", "D"],
        }
    )
    payload = validate_matches_dataset(df, "v1")
    assert payload["required_fields_missing"] == []
    assert payload["match_id_generated"] is True
    assert payload["duplicate_match_id_count"] == 0


def test_validate_matches_dataset_duplicate_match_id_detected_after_generation(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    df = pd.DataFrame(
        {
            "date": ["2025-08-15", "2025-08-15"],
            "league": ["E0", "E0"],
            "home_team": ["Man United", "Man United"],
            "away_team": ["Fulham", "Fulham"],
            "odds_home": [1.6, 1.6],
            "odds_draw": [4.2, 4.2],
            "odds_away": [5.2, 5.2],
            "actual_result": ["H", "H"],
        }
    )
    payload = validate_matches_dataset(df, "v1")
    assert payload["match_id_generated"] is True
    assert payload["duplicate_match_id_count"] == 1


def test_match_id_generation_normalizes_fields_stably():
    df1 = pd.DataFrame(
        {
            "date": ["15/08/2025"],
            "league": ["E0"],
            "home_team": ["Man United"],
            "away_team": ["Crystal Palace"],
            "odds_home": [2.0],
            "odds_draw": [3.0],
            "odds_away": [4.0],
            "actual_result": ["H"],
        }
    )
    df2 = pd.DataFrame(
        {
            "date": ["2025-08-15"],
            "league": [" e0 "],
            "home_team": ["  man   united  "],
            "away_team": ["Crystal-Palace"],
            "odds_home": [2.0],
            "odds_draw": [3.0],
            "odds_away": [4.0],
            "actual_result": ["H"],
        }
    )

    out1, gen1 = ensure_match_id(df1)
    out2, gen2 = ensure_match_id(df2)
    assert gen1 is True
    assert gen2 is True
    assert str(out1["match_id"].iloc[0]) == str(out2["match_id"].iloc[0])
