from __future__ import annotations

from pathlib import Path

import pandas as pd

from data.api_football_odds_snapshot import (
    archive_api_football_odds_snapshots,
    normalize_api_football_asian_handicap,
)


def _mapping(*, kickoff: str = "2026-08-16T23:00:00+08:00") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_fixture_id": "1570339",
                "match_id": "2026-08-16|018",
                "competition_id": "ESP_LA_LIGA",
                "kickoff_at": kickoff,
                "home_team": "桑坦德",
                "away_team": "比利亚雷",
            }
        ]
    )


def _payload() -> dict:
    return {
        "errors": [],
        "response": [
            {
                "league": {"id": 140, "name": "La Liga"},
                "fixture": {"id": 1570339, "date": "2026-08-16T23:00:00+08:00"},
                "update": "2026-08-16T18:10:18+08:00",
                "bookmakers": [
                    {
                        "id": 8,
                        "name": "Bet365",
                        "bets": [
                            {
                                "id": 4,
                                "name": "Asian Handicap",
                                "values": [
                                    {"value": "Home -0.25", "odd": "2.85"},
                                    {"value": "Away -0.25", "odd": "1.40"},
                                    {"value": "Home +0", "odd": "2.42"},
                                    {"value": "Away +0", "odd": "1.52"},
                                    {"value": "Home +0.5", "odd": "1.70"},
                                    {"value": "Away +0.5", "odd": "2.10"},
                                ],
                            },
                            {
                                "id": 1,
                                "name": "Match Winner",
                                "values": [{"value": "Home", "odd": "3.00"}],
                            },
                        ],
                    }
                ],
            }
        ],
    }


def test_normalizer_preserves_exact_quarter_lines_and_home_view(tmp_path: Path) -> None:
    frame = normalize_api_football_asian_handicap(
        _payload(),
        mapping=_mapping(),
        captured_at="2026-08-16T20:00:00+08:00",
        snapshot_id="snap-1",
        raw_sha256="abc",
        raw_archive_path=tmp_path / "raw.json",
    )

    assert frame["home_handicap"].tolist() == [-0.25, 0.0, 0.5]
    assert frame["away_handicap"].tolist() == [0.25, -0.0, -0.5]
    quarter = frame.loc[frame["home_handicap"].eq(-0.25)].iloc[0]
    assert quarter["home_odds"] == 2.85
    assert quarter["away_odds"] == 1.40
    assert quarter["match_id"] == "2026-08-16|018"
    assert bool(quarter["before_kickoff"]) is True
    assert bool(quarter["eligible_for_research"]) is True
    assert frame["bet_name"].eq("Asian Handicap").all()
    assert frame["is_bookmaker_main_line"].sum() == 1
    assert frame.loc[frame["is_bookmaker_main_line"], "home_handicap"].iloc[0] == 0.5
    assert frame.loc[frame["is_bookmaker_main_line"], "primary_line_price_balanced"].all()
    assert frame["eligible_for_primary_research"].sum() == 1


def test_post_kickoff_and_ambiguous_mapping_are_archived_but_rejected(tmp_path: Path) -> None:
    ambiguous = pd.concat([_mapping(), _mapping()], ignore_index=True)
    ambiguous.loc[1, "match_id"] = "another-match"
    frame = normalize_api_football_asian_handicap(
        _payload(),
        mapping=ambiguous,
        captured_at="2026-08-17T00:00:00+08:00",
        snapshot_id="snap-2",
        raw_sha256="def",
        raw_archive_path=tmp_path / "raw.json",
    )

    assert frame["mapping_status"].eq("ambiguous").all()
    assert (~frame["before_kickoff"].astype(bool)).all()
    assert (~frame["eligible_for_research"].astype(bool)).all()
    assert (~frame["eligible_for_primary_research"].astype(bool)).all()
    assert frame["reject_reason"].str.contains("fixture_mapping_ambiguous").all()
    assert frame["reject_reason"].str.contains("captured_at_not_before_kickoff").all()


class _FakeClient:
    def __init__(self) -> None:
        self.last_headers = {
            "x-ratelimit-requests-limit": "100",
            "x-ratelimit-requests-remaining": "99",
            "x-ratelimit-limit": "10",
            "x-ratelimit-remaining": "9",
        }

    def get(self, endpoint: str, params: dict) -> dict:
        assert endpoint == "odds"
        assert params == {"fixture": "1570339"}
        return _payload()


def test_archive_is_immutable_and_idempotent(tmp_path: Path) -> None:
    kwargs = {
        "client": _FakeClient(),
        "mapping": _mapping(),
        "captured_at": "2026-08-16T20:00:00+08:00",
        "raw_root": tmp_path / "raw",
        "snapshot_root": tmp_path / "snapshots",
        "history_path": tmp_path / "history.csv",
    }
    first = archive_api_football_odds_snapshots(**kwargs)
    second = archive_api_football_odds_snapshots(**kwargs)
    history = pd.read_csv(tmp_path / "history.csv")

    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["asian_handicap_rows"] == 3
    assert first["eligible_rows"] == 3
    assert first["bookmaker_main_line_rows"] == 1
    assert first["primary_line_rows"] == 1
    assert first["quota"]["daily_remaining"] == "99"
    assert len(history) == 3
    assert len(list((tmp_path / "raw").rglob("*.json"))) == 1
    assert len(list((tmp_path / "snapshots").rglob("*.csv"))) == 2
    assert Path(first["snapshot_path"]).exists()
    assert Path(first["primary_snapshot_path"]).exists()
    assert len(pd.read_csv(first["primary_snapshot_path"])) == 1
