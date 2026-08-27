from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from data.the_odds_sporttery import (
    align_fixtures_to_odds,
    capture_sporttery_the_odds_snapshot,
    route_sport_keys,
)
from world_cup.the_odds_api_adapter import odds_payload_to_frame


def _fixture() -> dict[str, object]:
    return {
        "match_id": "2026-08-17|001",
        "match_number": "001",
        "competition": "英超",
        "competition_id": "ENG_PREMIER_LEAGUE",
        "home_team": "曼城",
        "away_team": "阿森纳",
        "home_team_canonical": "Manchester City",
        "away_team_canonical": "Arsenal",
        "kickoff": "2026-08-17T20:00:00+08:00",
        "sale_status": "on_sale",
    }


def _payload() -> list[dict[str, object]]:
    return [
        {
            "id": "event-1",
            "sport_key": "soccer_epl",
            "sport_title": "EPL",
            "commence_time": "2026-08-17T12:00:00Z",
            "home_team": "Manchester City",
            "away_team": "Arsenal",
            "bookmakers": [
                {
                    "key": "book-a",
                    "title": "Book A",
                    "last_update": "2026-08-17T10:00:00Z",
                    "markets": [
                        {
                            "key": "h2h",
                            "last_update": "2026-08-17T10:00:00Z",
                            "outcomes": [
                                {"name": "Manchester City", "price": 1.8},
                                {"name": "Draw", "price": 3.6},
                                {"name": "Arsenal", "price": 4.2},
                            ],
                        },
                        {
                            "key": "spreads",
                            "last_update": "2026-08-17T10:00:00Z",
                            "outcomes": [
                                {"name": "Manchester City", "price": 1.95, "point": -0.5},
                                {"name": "Arsenal", "price": 1.9, "point": 0.5},
                            ],
                        },
                    ],
                }
            ],
        }
    ]


def test_routes_confirmed_fixture_by_competition_id():
    keys, unrouted = route_sport_keys([_fixture()])

    assert keys == ["soccer_epl"]
    assert unrouted == []


def test_alignment_requires_canonical_teams_and_kickoff_tolerance():
    odds = odds_payload_to_frame(_payload())
    aligned = align_fixtures_to_odds(
        [_fixture()], odds, captured_at="2026-08-17T10:00:00Z"
    )

    assert aligned.iloc[0]["mapping_status"] == "mapped"
    assert aligned.iloc[0]["event_id"] == "event-1"
    assert aligned.iloc[0]["kickoff_delta_minutes"] == 0
    assert aligned.iloc[0]["market_keys"] == "h2h,spreads"


def test_snapshot_is_immutable_audited_and_never_writes_ledger(tmp_path):
    def fake_fetcher(client, **kwargs):
        client.last_headers = {"x-requests-remaining": "499", "x-requests-used": "1"}
        assert kwargs["sport_key"] == "soccer_epl"
        return _payload()

    scan = {"sales_day": "2026-08-17", "fixtures": [_fixture()]}
    first = capture_sporttery_the_odds_snapshot(
        scan=scan,
        snapshot_root=tmp_path,
        api_key="test-key",
        snapshot_type="confirm",
        fetcher=fake_fetcher,
    )
    second = capture_sporttery_the_odds_snapshot(
        scan=scan,
        snapshot_root=tmp_path,
        api_key="test-key",
        snapshot_type="confirm",
        fetcher=fake_fetcher,
    )

    assert first["status"] == "complete"
    assert first["mapped_fixtures"] == 1
    assert first["ledger_write_performed"] is False
    assert first["snapshot_dir"] != second["snapshot_dir"]
    for name in ("raw_payload.json", "odds.csv", "match_market_summary.csv", "sporttery_alignment.csv", "audit.json"):
        assert (Path(first["snapshot_dir"]) / name).exists()
    raw = json.loads((Path(first["snapshot_dir"]) / "raw_payload.json").read_text(encoding="utf-8"))
    assert raw["soccer_epl"][0]["id"] == "event-1"
    alignment = pd.read_csv(Path(first["snapshot_dir"]) / "sporttery_alignment.csv")
    assert alignment.iloc[0]["mapping_status"] == "mapped"


def test_unconfigured_snapshot_is_audited_without_network(tmp_path):
    audit = capture_sporttery_the_odds_snapshot(
        scan={"sales_day": "2026-08-17", "fixtures": [_fixture()]},
        snapshot_root=tmp_path,
        api_key="",
        snapshot_type="confirm",
    )

    assert audit["status"] == "not_configured"
    assert audit["requests"] == []
    assert audit["ledger_write_performed"] is False


def test_invalid_early_confirmation_cannot_fetch_external_odds(tmp_path):
    with pytest.raises(ValueError, match="invalid Sporttery scan"):
        capture_sporttery_the_odds_snapshot(
            scan={
                "stage": "confirm",
                "scan_stage_valid": False,
                "batch_status": "invalid_early_confirm",
                "fixtures": [_fixture()],
            },
            snapshot_root=tmp_path,
            api_key="test-key",
            snapshot_type="confirm",
        )

    assert list(tmp_path.iterdir()) == []
