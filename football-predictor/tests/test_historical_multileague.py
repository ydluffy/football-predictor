from __future__ import annotations

import json

import pandas as pd
import pytest

import data.historical_dataset as historical_dataset
from data.historical_dataset import (
    build_historical_dataset,
    download_football_data_files,
    load_division_profile,
)


def _raw_match(division: str, home: str, away: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Div": [division],
            "Date": ["12/08/2023"],
            "HomeTeam": [home],
            "AwayTeam": [away],
            "FTHG": [2],
            "FTAG": [1],
            "FTR": ["H"],
            "B365H": [2.0],
            "B365D": [3.2],
            "B365A": [4.0],
        }
    )


def _mapping(tmp_path):
    payload = {
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
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_named_profile_is_explicit_and_stable() -> None:
    assert load_division_profile("europe_top5") == ("E0", "SP1", "D1", "F1", "I1")
    with pytest.raises(ValueError, match="unknown historical data profile"):
        load_division_profile("missing")


def test_candidate_build_filters_divisions_without_polluting_baseline(tmp_path) -> None:
    raw = tmp_path / "raw" / "2023-24"
    raw.mkdir(parents=True)
    _raw_match("E0", "Arsenal", "Chelsea").to_csv(raw / "E0.csv", index=False)
    _raw_match("SP1", "Barcelona", "Sevilla").to_csv(raw / "SP1.csv", index=False)

    output, audit = build_historical_dataset(
        input_dir=tmp_path / "raw",
        mapping_path=_mapping(tmp_path),
        output_path=tmp_path / "out.csv",
        audit_path=tmp_path / "audit.json",
        divisions=["SP1"],
    )

    assert output["league"].tolist() == ["SP1"]
    assert audit["selected_divisions"] == ["SP1"]
    assert audit["source_file_count"] == 1


class _Response:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.content


def test_invalid_download_never_overwrites_existing_csv(tmp_path, monkeypatch) -> None:
    target = tmp_path / "2023-24" / "SP1.csv"
    target.parent.mkdir(parents=True)
    target.write_text("known-good", encoding="utf-8")
    monkeypatch.setattr(historical_dataset, "urlopen", lambda *_args, **_kwargs: _Response(b"not,a,match\n1,2,3\n"))

    with pytest.raises(ValueError, match="missing columns"):
        download_football_data_files(output_dir=tmp_path, seasons=["2023-24"], divisions=["SP1"])

    assert target.read_text(encoding="utf-8") == "known-good"
    assert not target.with_suffix(".csv.part").exists()
