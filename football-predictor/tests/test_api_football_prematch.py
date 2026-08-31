from __future__ import annotations

from pathlib import Path

import pandas as pd

from data.api_football_prematch import (
    api_football_frames_to_prematch_intelligence,
    append_validated_prematch_intelligence,
    build_api_football_match_mapping,
)


def _mapping() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_fixture_id": "123",
                "match_id": "local-001",
                "competition_id": "ENG_PREMIER_LEAGUE",
                "kickoff_at": "2026-08-15T14:00:00Z",
                "home_team": "Manchester United",
                "away_team": "Arsenal",
            }
        ]
    )


def test_api_football_conversion_requires_explicit_fixture_mapping(tmp_path: Path) -> None:
    fixtures = pd.DataFrame(
        [{"source_fixture_id": "123", "home_team": "Man United", "away_team": "Arsenal"}]
    )
    absences = pd.DataFrame(
        [
            {
                "source_fixture_id": "123",
                "team": "Man United",
                "player": "Player A",
                "status": "injured",
                "impact": 1.5,
                "reason": "knee",
            },
            {
                "source_fixture_id": "999",
                "team": "Unknown",
                "player": "Player B",
                "status": "injured",
            },
        ]
    )
    lineups = pd.DataFrame(
        [
            {"match_id": "123", "team": "Arsenal", "player": f"A{i}", "role": "starter", "confirmed": 1}
            for i in range(11)
        ]
    )
    converted, audit = api_football_frames_to_prematch_intelligence(
        fixtures=fixtures,
        absences=absences,
        lineups=lineups,
        mapping=_mapping(),
        observed_at="2026-08-15T12:00:00Z",
    )
    assert len(converted) == 12
    assert audit["unmapped_fixture_ids"] == ["999"]
    assert converted.loc[converted["signal_type"].eq("absence"), "team"].iloc[0] == "Manchester United"

    write_audit = append_validated_prematch_intelligence(
        converted,
        manual_path=tmp_path / "manual.csv",
        validated_path=tmp_path / "validated.csv",
    )
    assert write_audit["validated_rows"] == 12
    assert pd.read_csv(tmp_path / "validated.csv").shape[0] == 12


def test_post_kickoff_api_rows_are_retained_raw_but_rejected_from_validated(tmp_path: Path) -> None:
    converted, _ = api_football_frames_to_prematch_intelligence(
        fixtures=pd.DataFrame([{"source_fixture_id": "123", "home_team": "Man United", "away_team": "Arsenal"}]),
        absences=pd.DataFrame(
            [{"source_fixture_id": "123", "team": "Man United", "player": "P", "status": "injured", "impact": 1.0}]
        ),
        lineups=pd.DataFrame(),
        mapping=_mapping(),
        observed_at="2026-08-15T15:00:00Z",
    )
    audit = append_validated_prematch_intelligence(
        converted,
        manual_path=tmp_path / "manual.csv",
        validated_path=tmp_path / "validated.csv",
    )
    assert audit["manual_rows"] == 1
    assert audit["validated_rows"] == 0
    assert audit["post_kickoff_rows"] == 1


def test_automatic_mapping_requires_unique_team_and_time_match() -> None:
    local = pd.DataFrame(
        [
            {
                "match_id": "2026-08-15|001",
                "competition_id": "ENG_PREMIER_LEAGUE",
                "kickoff": "2026-08-15T14:00:00Z",
                "home_team": "Man United",
                "away_team": "Arsenal",
                "home_team_canonical": "Manchester United",
                "away_team_canonical": "Arsenal",
            }
        ]
    )
    api = pd.DataFrame(
        [
            {
                "source_fixture_id": "123",
                "kickoff_time": "2026-08-15T14:05:00Z",
                "home_team": "Manchester United",
                "away_team": "Arsenal",
            }
        ]
    )
    mapping, audit = build_api_football_match_mapping(local, api)
    assert mapping.loc[0, "source_fixture_id"] == "123"
    assert audit["mapped_rows"] == 1
