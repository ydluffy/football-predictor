from __future__ import annotations

from pathlib import Path

import pandas as pd

from data.sporttery_snapshot_archive import archive_sporttery_scan_inputs


def test_snapshot_archive_is_immutable_and_idempotent(tmp_path: Path) -> None:
    official = tmp_path / "official.csv"
    official.write_text("match_number,spf_odds_home\n002,1.80\n", encoding="utf-8")
    plays = tmp_path / "plays.csv"
    plays.write_text("match_number,play_type\n002,total_goals\n", encoding="utf-8")
    scan = {
        "stage": "confirm",
        "sales_day": "2026-08-10",
        "scanned_at": "2026-08-10T11:05:00+08:00",
        "fixtures": [{"match_number": "002", "kickoff": "2026-08-10T20:00:00+08:00"}],
    }
    kwargs = {
        "official_markets_path": official,
        "play_odds_path": plays,
        "scan": scan,
        "archive_root": tmp_path / "archive",
        "index_path": tmp_path / "index.csv",
    }
    first = archive_sporttery_scan_inputs(**kwargs)
    second = archive_sporttery_scan_inputs(**kwargs)
    index = pd.read_csv(tmp_path / "index.csv")
    assert first["snapshot_id"] == second["snapshot_id"]
    assert len(index) == 2
    assert index["all_fixtures_before_kickoff"].all()
    assert index["fixtures_before_kickoff_count"].eq(1).all()
    assert index["safe_match_numbers"].astype(str).eq("2").all() or index["safe_match_numbers"].astype(str).eq("002").all()
    assert all(Path(path).exists() for path in index["archive_path"])


def test_snapshot_marks_post_kickoff_capture_unsafe(tmp_path: Path) -> None:
    official = tmp_path / "official.csv"
    official.write_text("match_number\n002\n", encoding="utf-8")
    plays = tmp_path / "plays.csv"
    plays.write_text("match_number\n002\n", encoding="utf-8")
    metadata = archive_sporttery_scan_inputs(
        official_markets_path=official,
        play_odds_path=plays,
        scan={
            "stage": "confirm",
            "sales_day": "2026-08-10",
            "scanned_at": "2026-08-10T21:00:00+08:00",
            "fixtures": [{"match_number": "002", "kickoff": "2026-08-10T20:00:00+08:00"}],
        },
        archive_root=tmp_path / "archive",
        index_path=tmp_path / "index.csv",
    )
    assert metadata["all_fixtures_before_kickoff"] is False
    assert metadata["unsafe_match_numbers"] == ["002"]


def test_snapshot_archives_bom_only_failed_source_without_crashing(tmp_path: Path) -> None:
    official = tmp_path / "official.csv"
    official.write_bytes(b"\xef\xbb\xbf")
    plays = tmp_path / "plays.csv"
    plays.write_bytes(b"\xef\xbb\xbf")
    metadata = archive_sporttery_scan_inputs(
        official_markets_path=official,
        play_odds_path=plays,
        scan={
            "stage": "confirm",
            "sales_day": "2026-08-16",
            "scanned_at": "2026-08-16T22:00:00+08:00",
            "fixtures": [],
        },
        archive_root=tmp_path / "archive",
        index_path=tmp_path / "index.csv",
    )
    assert [item["rows"] for item in metadata["files"]] == [0, 0]
    assert all(Path(item["archive_path"]).read_bytes() == b"\xef\xbb\xbf" for item in metadata["files"])
