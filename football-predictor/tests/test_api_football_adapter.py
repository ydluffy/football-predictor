from __future__ import annotations

import pandas as pd
import requests
from unittest.mock import Mock

from world_cup.api_football_adapter import ApiFootballClient
from world_cup.api_football_adapter import api_fixture_rows_to_frame
from world_cup.api_football_adapter import import_api_football_realtime
from world_cup.api_football_adapter import injury_rows_to_absences
from world_cup.api_football_adapter import lineup_rows_to_realtime_lineups


def test_api_football_client_uses_header_and_redacts_transport_errors(monkeypatch):
    response = Mock()
    response.headers = {}
    response.raise_for_status.return_value = None
    response.json.return_value = {"response": []}
    request = Mock(return_value=response)
    monkeypatch.setattr("world_cup.api_football_adapter.requests.get", request)

    ApiFootballClient(api_key="secret").get("status")  # pragma: allowlist secret

    _, kwargs = request.call_args
    assert kwargs["headers"] == {"x-apisports-key": "secret"}
    assert "secret" not in kwargs["params"]

    def fail_request(*args, **kwargs):
        raise requests.ConnectionError(f"failed with {kwargs['headers']['x-apisports-key']}")

    monkeypatch.setattr("world_cup.api_football_adapter.requests.get", fail_request)
    try:
        ApiFootballClient(api_key="secret").get("status")  # pragma: allowlist secret
    except RuntimeError as exc:
        assert str(exc) == "API-Football request failed (network_error)"
        assert "secret" not in str(exc)
    else:
        raise AssertionError("expected a sanitized transport failure")


def test_api_football_rows_convert_to_model_inputs():
    fixtures = api_fixture_rows_to_frame(
        [
            {
                "fixture": {
                    "id": 123,
                    "date": "2026-06-26T04:00:00+00:00",
                    "venue": {"name": "Arena", "city": "City"},
                    "status": {"short": "NS"},
                },
                "league": {"id": 1, "name": "World Cup", "season": 2026},
                "teams": {
                    "home": {"name": "Ecuador"},
                    "away": {"name": "Germany"},
                },
            }
        ]
    )
    absences = injury_rows_to_absences(
        [
            {
                "fixture": {"id": 123, "date": "2026-06-26T04:00:00+00:00"},
                "team": {"name": "Germany"},
                "player": {"id": 9, "name": "Player A", "type": "Injury", "reason": "Knee"},
            }
        ]
    )
    lineups = lineup_rows_to_realtime_lineups(
        [
            {
                "team": {"name": "Germany"},
                "startXI": [{"player": {"id": i, "name": f"G{i}"}} for i in range(11)],
                "substitutes": [{"player": {"id": 20, "name": "Sub"}}],
            }
        ],
        fixture_id=123,
    )

    assert fixtures.loc[0, "source_fixture_id"] == "123"
    assert fixtures.loc[0, "home_team"] == "Ecuador"
    assert absences.loc[0, "status"] == "injured"
    assert absences.loc[0, "team"] == "Germany"
    assert len(lineups[lineups["role"].eq("starter")]) == 11
    assert set(lineups["source"]) == {"api_football"}


def test_api_football_import_writes_empty_outputs_without_key(tmp_path):
    audit = import_api_football_realtime(
        output_dir=tmp_path,
        league_id=1,
        season=2026,
        api_key="",
    )

    assert audit["status"] == "skipped"
    assert (tmp_path / "fixtures.csv").exists()
    assert (tmp_path / "absences.csv").exists()
    assert (tmp_path / "realtime_lineups.csv").exists()
    assert pd.read_csv(tmp_path / "absences.csv").empty
