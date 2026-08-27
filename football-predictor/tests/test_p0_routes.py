from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from api import main as api_main
from api.routes import p0 as p0_routes
from p0.db import connect, upsert_fixtures


def _fixture(
    fixture_id: int,
    utc_date: str,
    home_team_id: int,
    away_team_id: int,
    *,
    status: str = "FINISHED",
    home_score: int | None = 1,
    away_score: int | None = 0,
) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "competition_code": "TEST",
        "competition_name": "Test League",
        "season": 2026,
        "matchday": 1,
        "utc_date": utc_date,
        "status": status,
        "home_team_id": home_team_id,
        "home_team_name": f"Team {home_team_id}",
        "away_team_id": away_team_id,
        "away_team_name": f"Team {away_team_id}",
        "home_score": home_score,
        "away_score": away_score,
    }


def _seed_database(monkeypatch, tmp_path: Path) -> Path:
    db_path = tmp_path / "p0.sqlite3"
    monkeypatch.setenv("P0_DB_PATH", str(db_path))
    conn = connect(db_path)
    try:
        upsert_fixtures(
            conn,
            [
                _fixture(1, "2026-06-01T18:00:00Z", 10, 30, home_score=2),
                _fixture(2, "2026-06-02T18:00:00Z", 40, 20, away_score=2),
                _fixture(
                    10,
                    "2026-06-10T18:00:00Z",
                    10,
                    20,
                    status="SCHEDULED",
                    home_score=None,
                    away_score=None,
                ),
            ],
        )
    finally:
        conn.close()
    return db_path


def test_fixture_and_prediction_routes_use_p0_database(monkeypatch, tmp_path) -> None:
    _seed_database(monkeypatch, tmp_path)

    fixtures = p0_routes.p0_list_fixtures(date="2026-06-10")
    predictions = p0_routes.p0_predict(
        p0_routes.P0PredictionsRequest(fixture_ids=[10])
    )

    assert fixtures.count == 1
    assert fixtures.fixtures[0].fixture_id == 10
    assert predictions.count == 1
    assert predictions.predictions[0].fixture_id == 10
    assert sum(
        (
            predictions.predictions[0].p_home,
            predictions.predictions[0].p_draw,
            predictions.predictions[0].p_away,
        )
    ) == pytest.approx(1.0)
    assert predictions.predictions[0].factors[0].startswith("主队近")
    assert predictions.predictions[0].factors[2].startswith("泊松期望进球")


def test_ingest_route_persists_fetched_fixtures(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "p0.sqlite3"
    monkeypatch.setenv("P0_DB_PATH", str(db_path))
    monkeypatch.setattr(
        p0_routes,
        "fetch_major_league_matches",
        lambda date_from, date_to: [
            _fixture(
                20,
                f"{date_from}T18:00:00Z",
                50,
                60,
                status="SCHEDULED",
                home_score=None,
                away_score=None,
            )
        ],
    )

    response = p0_routes.p0_ingest_football_data("2026-06-11", "2026-06-11")

    assert response.inserted_or_updated == 1
    assert response.db_path == str(db_path)
    assert p0_routes.p0_list_fixtures(date="2026-06-11").count == 1


def test_main_preserves_p0_exports_and_chinese_chat_intent(monkeypatch) -> None:
    connection = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(api_main, "p0_db_connect", lambda: connection)
    monkeypatch.setattr(
        api_main,
        "p0_select_fixtures_by_date",
        lambda conn, date_from, date_to: [],
    )

    response = api_main.p0_chat(
        api_main.ChatRequest(
            messages=[api_main.ChatMessage(role="user", content="今天有什么比赛？")]
        )
    )

    assert api_main.P0PredictionsRequest is p0_routes.P0PredictionsRequest
    assert "今日赛程" in response.content
    assert "先导入" in response.content


def test_api_source_contains_no_known_mojibake_sequences() -> None:
    source = Path(api_main.__file__).read_text(encoding="utf-8")

    for marker in ("ä¸", "èµ", "æ¯", "ï¼", "ã€", "ðŸ", "âš"):
        assert marker not in source
