from __future__ import annotations

import json

import pandas as pd

from data.historical_dataset import build_historical_dataset, infer_season, season_code


def test_season_code_and_inference():
    assert season_code("2020-21") == "2021"
    assert season_code("2023-24") == "2324"
    out = infer_season(pd.Series(["2024-08-10", "2025-05-01"]))
    assert out.tolist() == ["2024-25", "2024-25"]


def test_build_historical_dataset_combines_and_deduplicates(tmp_path):
    raw_dir = tmp_path / "raw" / "2023-24"
    raw_dir.mkdir(parents=True)
    raw = pd.DataFrame(
        {
            "Div": ["E0", "E0"],
            "Date": ["12/08/2023", "12/08/2023"],
            "HomeTeam": ["A", "A"],
            "AwayTeam": ["B", "B"],
            "FTHG": [2, 2],
            "FTAG": [1, 1],
            "FTR": ["H", "H"],
            "B365H": [2.0, 2.0],
            "B365D": [3.2, 3.2],
            "B365A": [4.0, 4.0],
            "B365CH": [1.9, 1.9],
            "B365CD": [3.3, 3.3],
            "B365CA": [4.2, 4.2],
        }
    )
    raw.to_csv(raw_dir / "E0.csv", index=False)
    mapping = {
        "fields": {
            "Div": "league",
            "Date": "date",
            "HomeTeam": "home_team",
            "AwayTeam": "away_team",
            "FTHG": "home_goals",
            "FTAG": "away_goals",
            "FTR": "actual_result",
            "B365H": "odds_home",
            "B365D": "odds_draw",
            "B365A": "odds_away",
        },
        "required_standard_fields": ["odds_home", "odds_draw", "odds_away", "actual_result"],
    }
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")

    out, audit = build_historical_dataset(
        input_dir=tmp_path / "raw",
        mapping_path=mapping_path,
        output_path=tmp_path / "out.csv",
        audit_path=tmp_path / "audit.json",
    )

    assert len(out) == 1
    assert out.loc[0, "season"] == "2023-24"
    assert audit["duplicate_match_id_count"] == 1


def test_build_historical_dataset_accepts_cp1252(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    content = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A\n"
        "E0,12/08/2023,O’Connor FC,B,2,1,H,2.0,3.2,4.0\n"
    )
    (raw_dir / "E0.csv").write_bytes(content.encode("cp1252"))
    mapping = {
        "fields": {
            "Div": "league",
            "Date": "date",
            "HomeTeam": "home_team",
            "AwayTeam": "away_team",
            "FTHG": "home_goals",
            "FTAG": "away_goals",
            "FTR": "actual_result",
            "B365H": "odds_home",
            "B365D": "odds_draw",
            "B365A": "odds_away",
        },
        "required_standard_fields": ["odds_home", "odds_draw", "odds_away", "actual_result"],
    }
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")

    out, _ = build_historical_dataset(
        input_dir=raw_dir,
        mapping_path=mapping_path,
        output_path=tmp_path / "out.csv",
        audit_path=tmp_path / "audit.json",
    )

    assert len(out) == 1
