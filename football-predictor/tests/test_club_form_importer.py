from __future__ import annotations

import pandas as pd
import pytest

from world_cup.club_form_importer import import_club_form_csv, normalize_club_form_input
from world_cup.player_data import PlayerDataBundle, load_player_data_bundle
from world_cup.player_strength import build_player_strengths


def _write_bundle(root):
    root.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "player_id": "p1",
                "canonical_name": "Player One",
                "national_team": "A",
                "date_of_birth": "2000-01-01",
                "primary_position": "Forward",
            },
            {
                "player_id": "p2",
                "canonical_name": "Player Two",
                "national_team": "A",
                "date_of_birth": "2000-01-01",
                "primary_position": "Forward",
            },
        ]
    ).to_csv(root / "players.csv", index=False)
    pd.DataFrame(
        [
            {
                "source": "provider",
                "source_player_id": "10",
                "source_name": "Player One",
                "player_id": "p1",
            }
        ]
    ).to_csv(root / "player_aliases.csv", index=False)
    pd.DataFrame(
        [
            {
                "snapshot_date": "2026-06-15",
                "team": "A",
                "player_id": "p1",
                "role": "starter",
                "position": "Forward",
                "club": "Club",
            },
            {
                "snapshot_date": "2026-06-15",
                "team": "A",
                "player_id": "p2",
                "role": "starter",
                "position": "Forward",
                "club": "Club",
            },
        ]
    ).to_csv(root / "squads.csv", index=False)
    pd.DataFrame(columns=["as_of_date", "team", "player_id", "status", "reason"]).to_csv(
        root / "availability.csv",
        index=False,
    )
    pd.DataFrame(
        columns=[
            "match_date",
            "player_id",
            "club",
            "competition",
            "minutes",
            "started",
            "goals",
            "assists",
            "xg",
            "xa",
        ]
    ).to_csv(root / "club_appearances.csv", index=False)
    pd.DataFrame(columns=["match_date", "team", "opponent", "player_id", "started", "minutes"]).to_csv(
        root / "national_appearances.csv",
        index=False,
    )


def test_normalize_club_form_resolves_alias_when_player_id_blank(tmp_path):
    data_dir = tmp_path / "data"
    _write_bundle(data_dir)
    input_path = tmp_path / "club.csv"
    pd.DataFrame(
        [
            {
                "source": "provider",
                "source_player_id": "10",
                "player_id": "",
                "match_date": "2026-05-20",
                "club": "Club",
                "competition": "League",
                "minutes": 90,
                "started": "true",
                "goals": 1,
                "assists": 1,
                "xg": 0.5,
                "xa": 0.2,
            }
        ]
    ).to_csv(input_path, index=False)
    bundle = load_player_data_bundle(data_dir)

    out = normalize_club_form_input(input_path, bundle)

    assert out.loc[0, "player_id"] == "p1"
    assert bool(out.loc[0, "started"]) is True


def test_import_club_form_updates_contract_and_strength(tmp_path):
    data_dir = tmp_path / "data"
    _write_bundle(data_dir)
    input_path = tmp_path / "club.csv"
    pd.DataFrame(
        [
            {
                "player_id": "p1",
                "match_date": "2026-05-20",
                "club": "Club",
                "competition": "League",
                "minutes": 90,
                "started": True,
                "goals": 1,
                "assists": 0,
                "xg": 0.7,
                "xa": 0.1,
            }
        ]
    ).to_csv(input_path, index=False)

    audit = import_club_form_csv(
        player_data_dir=data_dir,
        input_path=input_path,
        as_of_date="2026-06-16",
    )
    bundle = load_player_data_bundle(data_dir)
    strengths = build_player_strengths(bundle, as_of_date="2026-06-16").set_index("player_id")

    assert audit["recent_player_coverage"] == pytest.approx(0.5)
    assert len(bundle.club_appearances) == 1
    assert strengths.loc["p1", "club_minutes_score"] > strengths.loc["p2", "club_minutes_score"]
    assert strengths.loc["p1", "relative_player_strength"] > strengths.loc["p2", "relative_player_strength"]
