from __future__ import annotations

import json

import pandas as pd
import pytest

from config.settings import get_settings
from ingest.real_data_ingest import ingest_matches_csv


def test_ingest_matches_csv_explicit_mapping_writes_outputs(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    ext = root / "data" / "external"
    ext.mkdir(parents=True, exist_ok=True)

    src = pd.DataFrame(
        {
            "Date": ["2025-01-01", "2025-01-02", "2025-01-03"],
            "League": ["EPL", "EPL", "LaLiga"],
            "Home": ["A", "B", "C"],
            "Away": ["D", "E", "F"],
            "HomeOdds": [2.1, 1.9, 2.5],
            "DrawOdds": [3.2, 3.4, 3.1],
            "AwayOdds": [3.5, 4.2, 2.9],
            "FTR": ["H", "D", "A"],
        }
    )
    inp = ext / "source.csv"
    src.to_csv(inp, index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()
    settings = get_settings()

    mapping = {
        "date": "Date",
        "league": "League",
        "home_team": "Home",
        "away_team": "Away",
        "odds_home": "HomeOdds",
        "odds_draw": "DrawOdds",
        "odds_away": "AwayOdds",
        "actual_result": "FTR",
        "match_id": ["id", "match_id"],
    }

    out = ingest_matches_csv(inp, mapping_spec=mapping, feature_version="v1")
    assert out.output_path.exists()
    assert out.mapping_record_path.exists()
    assert out.validation_path.exists()
    assert out.missing_report_path.exists()

    df_out = pd.read_csv(out.output_path)
    assert {"match_id", "odds_home", "odds_draw", "odds_away", "actual_result"} <= set(df_out.columns)

    record = json.loads(out.mapping_record_path.read_text(encoding="utf-8"))
    assert record["feature_version"] == "v1"


def test_ingest_matches_csv_auto_mapping_works(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    ext = root / "data" / "external"
    ext.mkdir(parents=True, exist_ok=True)

    src = pd.DataFrame(
        {
            "date": ["2025-01-01", "2025-01-02", "2025-01-03"],
            "league": ["EPL", "EPL", "LaLiga"],
            "HomeTeam": ["A", "B", "C"],
            "AwayTeam": ["D", "E", "F"],
            "B365H": [2.1, 1.9, 2.5],
            "B365D": [3.2, 3.4, 3.1],
            "B365A": [3.5, 4.2, 2.9],
            "FTR": ["H", "D", "A"],
        }
    )
    inp = ext / "source2.csv"
    src.to_csv(inp, index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    out = ingest_matches_csv(inp, mapping_spec=None, feature_version="v1")
    df_out = pd.read_csv(out.output_path)
    assert df_out["actual_result"].isin(["H", "D", "A"]).all()


def test_ingest_matches_csv_missing_required_raises(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    ext = root / "data" / "external"
    ext.mkdir(parents=True, exist_ok=True)

    src = pd.DataFrame({"HomeOdds": [2.0], "DrawOdds": [3.0]})
    inp = ext / "bad.csv"
    src.to_csv(inp, index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    with pytest.raises(ValueError):
        ingest_matches_csv(inp, mapping_spec=None, feature_version="v1")


def test_ingest_matches_csv_allows_custom_artifact_paths(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    ext = root / "data" / "external"
    ext.mkdir(parents=True, exist_ok=True)

    src = pd.DataFrame(
        {
            "date": ["2025-01-01"],
            "league": ["EPL"],
            "home_team": ["A"],
            "away_team": ["B"],
            "odds_home": [2.0],
            "odds_draw": [3.0],
            "odds_away": [4.0],
            "actual_result": ["H"],
        }
    )
    inp = ext / "source3.csv"
    src.to_csv(inp, index=False)

    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    out_csv = root / "custom" / "standardized.csv"
    map_json = root / "custom" / "map.json"
    val_json = root / "custom" / "val.json"
    miss_csv = root / "custom" / "miss.csv"

    out = ingest_matches_csv(
        inp,
        output_csv_path=out_csv,
        mapping_record_path=map_json,
        validation_path=val_json,
        missing_report_path=miss_csv,
        feature_version="v1",
    )
    assert out.output_path == out_csv
    assert out.mapping_record_path == map_json
    assert out.validation_path == val_json
    assert out.missing_report_path == miss_csv
    assert out_csv.exists()
    assert map_json.exists()
    assert val_json.exists()
    assert miss_csv.exists()
