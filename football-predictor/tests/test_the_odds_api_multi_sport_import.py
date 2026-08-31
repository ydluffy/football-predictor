from __future__ import annotations

import pandas as pd

import scripts.import_the_odds_api_multi_sport as multi


def test_parse_sport_keys_defaults_and_custom_values():
    assert "soccer_fifa_world_cup" in multi.parse_sport_keys("")
    assert multi.parse_sport_keys(" soccer_usa_mls, soccer_brazil_campeonato ") == [
        "soccer_usa_mls",
        "soccer_brazil_campeonato",
    ]


def test_multi_sport_import_writes_empty_outputs_without_key(tmp_path):
    audit = multi.import_multi_sport_odds(
        output_dir=tmp_path,
        api_key="",
        sport_keys=["soccer_usa_mls"],
        regions="eu",
        markets="h2h",
        bookmakers="",
        timeout=5,
    )

    assert audit["status"] == "skipped"
    assert (tmp_path / "odds.csv").exists()
    assert (tmp_path / "match_market_summary.csv").exists()
    assert pd.read_csv(tmp_path / "odds.csv").empty


def test_multi_sport_import_combines_successful_sports(monkeypatch, tmp_path):
    payload_by_sport = {
        "soccer_usa_mls": [
            {
                "id": "mls_1",
                "sport_key": "soccer_usa_mls",
                "sport_title": "MLS",
                "commence_time": "2026-07-18T02:00:00Z",
                "home_team": "Nashville SC",
                "away_team": "Atlanta United",
                "bookmakers": [
                    {
                        "key": "book_a",
                        "title": "Book A",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Nashville SC", "price": 1.8},
                                    {"name": "Draw", "price": 3.4},
                                    {"name": "Atlanta United", "price": 4.2},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
        "soccer_brazil_campeonato": [
            {
                "id": "bra_1",
                "sport_key": "soccer_brazil_campeonato",
                "sport_title": "Brazil Serie A",
                "commence_time": "2026-07-18T01:00:00Z",
                "home_team": "Bahia",
                "away_team": "Chapecoense",
                "bookmakers": [
                    {
                        "key": "book_b",
                        "title": "Book B",
                        "markets": [
                            {
                                "key": "totals",
                                "outcomes": [
                                    {"name": "Over", "price": 1.9, "point": 2.5},
                                    {"name": "Under", "price": 1.9, "point": 2.5},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }

    def fake_fetch_odds(client, *, sport_key, regions, markets, bookmakers):
        return payload_by_sport[sport_key]

    monkeypatch.setattr(multi, "fetch_odds", fake_fetch_odds)

    audit = multi.import_multi_sport_odds(
        output_dir=tmp_path,
        api_key="token",  # pragma: allowlist secret
        sport_keys=["soccer_usa_mls", "soccer_brazil_campeonato"],
        regions="eu",
        markets="h2h,totals",
        bookmakers="",
        timeout=5,
    )
    odds = pd.read_csv(tmp_path / "odds.csv")
    summary = pd.read_csv(tmp_path / "match_market_summary.csv")

    assert audit["status"] == "ok"
    assert audit["events"] == 2
    assert set(odds["sport_key"]) == {"soccer_usa_mls", "soccer_brazil_campeonato"}
    assert set(summary["event_id"]) == {"mls_1", "bra_1"}


def test_multi_sport_import_keeps_partial_success(monkeypatch, tmp_path):
    def fake_fetch_odds(client, *, sport_key, regions, markets, bookmakers):
        if sport_key == "bad_sport":
            raise RuntimeError("sport unavailable")
        return [
            {
                "id": "ok_1",
                "sport_key": sport_key,
                "sport_title": "OK",
                "commence_time": "2026-07-18T02:00:00Z",
                "home_team": "France",
                "away_team": "England",
                "bookmakers": [],
            }
        ]

    monkeypatch.setattr(multi, "fetch_odds", fake_fetch_odds)

    audit = multi.import_multi_sport_odds(
        output_dir=tmp_path,
        api_key="token",  # pragma: allowlist secret
        sport_keys=["soccer_fifa_world_cup", "bad_sport"],
        regions="eu",
        markets="h2h",
        bookmakers="",
        timeout=5,
    )

    assert audit["status"] == "partial"
    assert [item["status"] for item in audit["sports"]] == ["ok", "error"]
    assert (tmp_path / "odds.csv").exists()
