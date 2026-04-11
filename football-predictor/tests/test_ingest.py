from __future__ import annotations

import pandas as pd

import pytest

from config.settings import get_settings
from ingest.load_data import REQUIRED_COLUMNS, load_matches, load_matches_with_meta


def test_load_matches_reads_and_outputs_standard_schema(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        {
            "match_id": [1, 2, 3],
            "odds_home": [1.9, 2.1, 1.8],
            "odds_draw": [3.2, 3.0, 3.4],
            "odds_away": [4.1, 3.7, 4.5],
            "actual_result": ["H", "D", "A"],
            "extra_col": [10, 11, 12],
        }
    )
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    loaded = load_matches("data/raw/sample_matches.csv")
    assert len(loaded) == 3
    assert list(loaded.columns) == REQUIRED_COLUMNS


def test_load_matches_missing_columns_raises(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame({"match_id": [1], "odds_home": [1.9]})
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        load_matches("data/raw/sample_matches.csv")


def test_load_matches_empty_data_raises(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(columns=REQUIRED_COLUMNS).to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        load_matches("data/raw/sample_matches.csv")


def test_load_matches_with_meta_keeps_odds_snapshot_columns_when_present(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        {
            "match_id": ["m1", "m2"],
            "odds_home": [1.9, 2.1],
            "odds_draw": [3.2, 3.0],
            "odds_away": [4.1, 3.7],
            "odds_home_open": [2.0, 2.0],
            "odds_home_last": [1.9, 2.1],
            "odds_draw_t1": [3.1, 3.0],
            "odds_draw_t2": [3.2, 2.9],
            "actual_result": ["H", "D"],
        }
    )
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    out = load_matches_with_meta("data/raw/sample_matches.csv", extra_columns=["date"])
    assert {"odds_home_open", "odds_home_last", "odds_draw_t1", "odds_draw_t2"} <= set(out.columns)


def test_load_matches_with_meta_works_without_snapshot_columns(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(
        {
            "match_id": ["m1"],
            "odds_home": [1.9],
            "odds_draw": [3.2],
            "odds_away": [4.1],
            "actual_result": ["H"],
        }
    )
    df.to_csv(raw / "sample_matches.csv", index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    out = load_matches_with_meta("data/raw/sample_matches.csv", extra_columns=["date"])
    assert list(out.columns) == REQUIRED_COLUMNS
