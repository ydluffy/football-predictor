from __future__ import annotations

import json
from types import SimpleNamespace

import pandas as pd

from config.settings import get_settings
from research_director.data_preflight import preflight_real_data


def test_preflight_missing_files(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    out = preflight_real_data(raw_matches_csv=root / "missing.csv", mapping_path=root / "missing.json")
    assert out.status == "review_required"
    assert "raw_csv_missing" in out.reasons
    assert "mapping_missing" in out.reasons


def test_preflight_mapping_missing_required_fields(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    raw = root / "data" / "external" / "a.csv"
    raw.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"x": [1]}).to_csv(raw, index=False)

    mapping = root / "data" / "mappings" / "m.json"
    mapping.parent.mkdir(parents=True, exist_ok=True)
    mapping.write_text(json.dumps({"required_standard_fields": ["odds_home"], "fields": {}}, ensure_ascii=False), encoding="utf-8")

    out = preflight_real_data(raw_matches_csv=raw, mapping_path=mapping)
    assert out.status == "review_required"
    assert "required_field_mapping_missing" in out.reasons


def test_preflight_ingest_ok_but_date_ratio_low(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    raw = root / "data" / "external" / "a.csv"
    raw.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"x": [1]}).to_csv(raw, index=False)

    mapping = root / "data" / "mappings" / "m.json"
    mapping.parent.mkdir(parents=True, exist_ok=True)
    mapping.write_text(
        json.dumps(
            {
                "required_standard_fields": ["odds_home", "odds_draw", "odds_away", "actual_result"],
                "fields": {"X": "odds_home", "Y": "odds_draw", "Z": "odds_away", "R": "actual_result", "D": "date"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def _fake_ingest_matches_csv(input_csv_path, **kwargs):
        s = get_settings()
        s.data_processed_dir.mkdir(parents=True, exist_ok=True)
        outp = s.data_processed_dir / "real_matches_standardized.csv"
        pd.DataFrame({"date": ["bad", "bad"], "odds_home": [2.0, 2.0], "odds_draw": [3.0, 3.0], "odds_away": [4.0, 4.0], "actual_result": ["H", "D"]}).to_csv(
            outp, index=False
        )
        v = s.artifacts_eval_dir / "dataset_validation.json"
        m = s.artifacts_eval_dir / "dataset_missing_report.csv"
        v.parent.mkdir(parents=True, exist_ok=True)
        v.write_text("{}", encoding="utf-8")
        m.write_text("field,exists\n", encoding="utf-8")
        return SimpleNamespace(output_path=outp, validation_path=v, missing_report_path=m)

    monkeypatch.setattr("research_director.data_preflight.ingest_matches_csv", _fake_ingest_matches_csv)

    out = preflight_real_data(raw_matches_csv=raw, mapping_path=mapping, min_rows=1, min_parseable_date_ratio=0.9)
    assert out.status == "review_required"
    assert "parseable_date_ratio_too_low" in out.reasons

