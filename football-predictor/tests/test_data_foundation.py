from __future__ import annotations

import json

import pandas as pd
import pytest

from config.settings import get_settings
from ingest.data_foundation import (
    assert_valid_matches_df,
    generate_mock_matches,
    get_schema_columns,
    validate_matches_df,
    write_matches_template_csv,
    write_mock_matches_csv,
    write_quality_reports,
)


def test_write_matches_template_csv_writes_header_and_example(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    p = write_matches_template_csv(include_optional=True, include_example_row=True)
    assert p == settings.data_matches_template_path
    df = pd.read_csv(p)
    assert set(get_schema_columns(include_optional=True)) <= set(df.columns)
    assert len(df) == 1


def test_generate_mock_matches_and_quality_reports(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    df = generate_mock_matches(n=60, seed=7, include_optional=True)
    report = validate_matches_df(df)
    assert report.errors == []
    assert report.n_rows == 60
    assert report.date_min is not None
    assert report.league_counts

    p_csv = write_mock_matches_csv(n=40, seed=3)
    assert p_csv == settings.data_mock_matches_path
    df2 = pd.read_csv(p_csv)
    assert_valid_matches_df(df2)

    report_path, missing_path = write_quality_reports(df2)
    assert report_path.exists()
    assert missing_path.exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert {"schema_version", "n_rows", "errors", "warnings", "missing_by_column"} <= set(payload.keys())
    miss = pd.read_csv(missing_path)
    assert {"column", "dtype", "missing_count", "missing_rate"} <= set(miss.columns)


def test_assert_valid_matches_df_missing_required_raises():
    df = pd.DataFrame({"match_id": ["m1"], "odds_home": [2.0], "odds_draw": [3.0], "actual_result": ["H"]})
    with pytest.raises(ValueError):
        assert_valid_matches_df(df)

