from __future__ import annotations

import pandas as pd
import pytest
from fastapi import HTTPException

from api import main as api_main
from api.routes import sporttery as sporttery_routes


def test_sporttery_handicap_market_api_returns_template_when_file_missing(
    monkeypatch,
    tmp_path,
):
    market_path = tmp_path / "missing.csv"
    fixtures = pd.DataFrame(
        [
            {
                "match_id": "760471",
                "date": "2026-06-25",
                "home_team": "Japan",
                "away_team": "Sweden",
            }
        ]
    )

    monkeypatch.setattr(sporttery_routes, "_sporttery_market_path", lambda run_date: market_path)
    monkeypatch.setattr(sporttery_routes, "_sporttery_template_rows", lambda run_date: fixtures.assign(
        match_number="",
        home_handicap="",
        source="sporttery_manual",
        updated_at="",
        notes="Fill from verified China Sports Lottery market.",
    )[[
        "date",
        "match_id",
        "match_number",
        "home_team",
        "away_team",
        "home_handicap",
        "source",
        "updated_at",
        "notes",
    ]])

    response = api_main.world_cup_sporttery_handicap_markets("2026-06-25")

    assert response.exists is False
    assert response.filled_count == 0
    assert response.rows[0].home_team == "Japan"
    assert response.rows[0].home_handicap is None


def test_sporttery_handicap_market_api_parses_filled_file(monkeypatch, tmp_path):
    market_path = tmp_path / "sporttery.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-06-25",
                "match_id": "760471",
                "match_number": "周四001",
                "home_team": "Japan",
                "away_team": "Sweden",
                "home_handicap": "主队让1球",
                "source": "sporttery_manual",
                "updated_at": "2026-06-25 10:00",
                "notes": "verified",
            }
        ]
    ).to_csv(market_path, index=False)

    monkeypatch.setattr(sporttery_routes, "_sporttery_market_path", lambda run_date: market_path)
    response = api_main.world_cup_sporttery_handicap_markets("2026-06-25")

    assert response.exists is True
    assert response.filled_count == 1
    assert response.rows[0].home_handicap_raw == "主队让1球"
    assert response.rows[0].home_handicap == -1.0


def test_sporttery_handicap_market_api_saves_csv(monkeypatch, tmp_path):
    market_path = tmp_path / "sporttery.csv"
    history_path = tmp_path / "history.csv"
    monkeypatch.setattr(sporttery_routes, "_sporttery_market_path", lambda run_date: market_path)
    monkeypatch.setattr(sporttery_routes, "_sporttery_market_history_path", lambda: history_path)

    response = api_main.save_world_cup_sporttery_handicap_markets(
        api_main.SportteryMarketSaveRequest(
            date="2026-06-25",
            snapshot_type="closing",
            captured_at="2026-06-25T18:00:00+08:00",
            rows=[
                api_main.SportteryMarketSaveRow(
                    date="2026-06-25",
                    match_id="760471",
                    match_number="周四001",
                    home_team="Japan",
                    away_team="Sweden",
                    home_handicap="主队让1球",
                    source="sporttery_manual",
                    updated_at="2026-06-25 10:00",
                    notes="verified",
                )
            ],
        )
    )

    assert response.ok is True
    assert response.filled_count == 1
    assert response.history_count == 1
    saved = pd.read_csv(market_path, encoding="utf-8-sig")
    history = pd.read_csv(history_path, encoding="utf-8-sig")
    assert saved.loc[0, "home_handicap"] == "主队让1球"
    assert saved.loc[0, "match_number"] == "周四001"
    assert history.loc[0, "snapshot_type"] == "closing"
    assert history.loc[0, "home_handicap"] == -1.0


def test_sporttery_handicap_market_api_rejects_bad_handicap(monkeypatch, tmp_path):
    market_path = tmp_path / "sporttery.csv"
    history_path = tmp_path / "history.csv"
    monkeypatch.setattr(sporttery_routes, "_sporttery_market_path", lambda run_date: market_path)
    monkeypatch.setattr(sporttery_routes, "_sporttery_market_history_path", lambda: history_path)

    with pytest.raises(HTTPException):
        api_main.save_world_cup_sporttery_handicap_markets(
            api_main.SportteryMarketSaveRequest(
                date="2026-06-25",
                rows=[
                    api_main.SportteryMarketSaveRow(
                        date="2026-06-25",
                        home_team="Japan",
                        away_team="Sweden",
                        home_handicap="看好主队",
                    )
                ],
            )
        )


def test_sporttery_paste_parse_api():
    response = api_main.parse_world_cup_sporttery_paste(
        api_main.SportteryPasteParseRequest(
            text="周四001\tJapan\tSweden\t主队让1球\n周四002\tEcuador\tGermany\t平手盘"
        )
    )

    assert response.count == 2
    assert response.rows[0]["match_number"] == "周四001"
    assert response.rows[0]["home_handicap"] == "主队让1球"


def test_sporttery_router_is_registered_once_and_main_exports_are_compatible():
    paths = [route.path for route in api_main.app.routes]
    assert paths.count("/world-cup/sporttery/handicap-markets") == 2
    assert paths.count("/world-cup/sporttery/parse-paste") == 1
    assert paths.count("/world-cup/sporttery/editor") == 1
    assert api_main.SportteryMarketSaveRequest is sporttery_routes.SportteryMarketSaveRequest
    assert (
        api_main.world_cup_sporttery_handicap_markets
        is sporttery_routes.world_cup_sporttery_handicap_markets
    )
