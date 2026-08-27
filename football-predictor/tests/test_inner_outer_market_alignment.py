from __future__ import annotations

import pandas as pd

from data.inner_outer_market_alignment import align_inner_outer_markets, load_sporttery_market_snapshots


def test_load_sporttery_market_snapshots_skips_bom_only_archive(tmp_path):
    empty_archive = tmp_path / "empty.csv"
    empty_archive.write_bytes(b"\xef\xbb\xbf")
    index = tmp_path / "index.csv"
    pd.DataFrame([{
        "source_type": "official_markets",
        "archive_path": str(empty_archive),
        "snapshot_id": "failed-snapshot",
        "captured_at": "2026-08-16T22:17:00+08:00",
        "sales_day": "2026-08-16",
    }]).to_csv(index, index=False)

    result = load_sporttery_market_snapshots(index)

    assert result.empty


def _inner() -> pd.DataFrame:
    return pd.DataFrame([{
        "match_id": "2026-08-16|018", "sales_day": "2026-08-16", "match_number": "018",
        "competition": "西甲", "home_team": "桑坦德", "away_team": "比利亚雷",
        "kickoff_time": "2026-08-16T23:00:00+08:00", "snapshot_id": "inner-1",
        "captured_at": "2026-08-16T20:00:00+08:00", "home_handicap": "-1",
        "rqspf_odds_home": "5.0", "rqspf_odds_draw": "4.0", "rqspf_odds_away": "1.5",
    }])


def _outer(captured_at: str) -> pd.DataFrame:
    return pd.DataFrame([{
        "record_id": "r1", "snapshot_id": "outer-1", "captured_at": captured_at,
        "source_fixture_id": "123", "match_id": "2026-08-16|018", "mapping_status": "mapped",
        "before_kickoff": True, "eligible_for_primary_research": True, "bookmaker_id": "1",
        "bookmaker_name": "Book", "home_handicap": -0.5, "home_odds": 1.9, "away_odds": 1.9,
    }])


def test_same_event_within_window_is_time_aligned():
    pairs, audit = align_inner_outer_markets(_inner(), _outer("2026-08-16T12:20:00Z"), max_delta_minutes=30)
    assert audit["identity_paired_events"] == 1
    assert audit["time_aligned_events"] == 1
    assert pairs.loc[0, "sporttery_minus_outer_handicap"] == -0.5


def test_same_event_outside_window_is_identity_only():
    pairs, audit = align_inner_outer_markets(_inner(), _outer("2026-08-16T14:00:00Z"), max_delta_minutes=30)
    assert audit["identity_paired_events"] == 1
    assert audit["time_aligned_events"] == 0
    assert pairs.loc[0, "time_aligned"] == False


def test_unmapped_outer_record_is_never_paired():
    outer = _outer("2026-08-16T12:20:00Z")
    outer.loc[0, "mapping_status"] = "ambiguous"
    pairs, audit = align_inner_outer_markets(_inner(), outer)
    assert pairs.empty
    assert audit["identity_paired_events"] == 0
