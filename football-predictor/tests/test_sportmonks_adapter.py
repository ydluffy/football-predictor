from __future__ import annotations

import pandas as pd
import requests
from unittest.mock import Mock

from world_cup.sportmonks_adapter import SportMonksClient
from world_cup.sportmonks_adapter import fetch_world_cup_fixtures
from world_cup.sportmonks_adapter import import_sportmonks_world_cup_realtime
from world_cup.sportmonks_adapter import lineup_rows_to_realtime_lineups
from world_cup.sportmonks_adapter import sidelined_rows_to_absences
from world_cup.sportmonks_adapter import sportmonks_fixture_rows_to_frame


def test_sportmonks_client_uses_authorization_header_not_query_token(monkeypatch):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"data": []}
    request = Mock(return_value=response)
    monkeypatch.setattr("world_cup.sportmonks_adapter.requests.get", request)

    SportMonksClient(api_token="secret").get("leagues", {"page": 1})

    _, kwargs = request.call_args
    assert kwargs["headers"] == {"Authorization": "secret"}
    assert "api_token" not in kwargs["params"]


def test_sportmonks_client_redacts_token_from_transport_errors(monkeypatch):
    def fail_request(*args, **kwargs):
        raise requests.ConnectionError(f"failed with {kwargs['headers']['Authorization']}")

    monkeypatch.setattr("world_cup.sportmonks_adapter.requests.get", fail_request)

    try:
        SportMonksClient(api_token="secret").get("leagues")
    except RuntimeError as exc:
        assert str(exc) == "SportMonks request failed (network_error)"
        assert "secret" not in str(exc)
    else:
        raise AssertionError("expected a sanitized transport failure")


def test_date_range_uses_between_endpoint_and_filters_season():
    client = Mock()
    client.get.return_value = {
        "data": [
            {"id": 1, "season_id": 27897},
            {"id": 2, "season_id": 99999},
        ]
    }

    rows = fetch_world_cup_fixtures(
        client,
        season_id=27897,
        date_from="2026-08-16",
        date_to="2026-08-17",
    )

    assert rows == [{"id": 1, "season_id": 27897}]
    endpoint, params = client.get.call_args.args
    assert endpoint == "fixtures/between/2026-08-16/2026-08-17"
    assert "filters" not in params


def test_sportmonks_payload_converts_to_realtime_model_inputs():
    fixture = {
        "id": 991,
        "starting_at": "2026-06-27T20:00:00Z",
        "participants": [
            {"name": "Germany", "meta": {"location": "home"}},
            {"name": "Ecuador", "meta": {"location": "away"}},
        ],
        "venue": {"name": "Arena"},
        "state": {"name": "Not Started"},
    }
    fixtures = sportmonks_fixture_rows_to_frame([fixture])
    absences = sidelined_rows_to_absences(
        [
            {
                "fixture_id": 991,
                "team": {"name": "Germany"},
                "player": {"display_name": "Player A"},
                "player_id": 7,
                "reason": "Suspended after red card",
                "type": "suspension",
            },
            {
                "fixture_id": 991,
                "team": {"name": "Ecuador"},
                "player": {"name": "Player B"},
                "player_id": 8,
                "reason": "Hamstring injury",
                "type": "injury",
            },
        ],
        fixture=fixture,
    )
    lineups = lineup_rows_to_realtime_lineups(
        [
            {
                "team": {"name": "Germany"},
                "player": {"display_name": f"G{i}"},
                "player_id": i,
                "formation_position": i,
            }
            for i in range(1, 12)
        ],
        fixture_id=991,
    )

    assert fixtures.loc[0, "source_fixture_id"] == "991"
    assert fixtures.loc[0, "home_team"] == "Germany"
    assert set(absences["status"]) == {"injured", "suspended"}
    assert set(absences["source"]) == {"sportmonks"}
    assert len(lineups[lineups["role"].eq("starter")]) == 11
    assert set(lineups["team"]) == {"Germany"}


def test_sportmonks_import_writes_empty_outputs_without_token(tmp_path):
    audit = import_sportmonks_world_cup_realtime(
        output_dir=tmp_path,
        season_id=12345,
        api_token="",
    )

    assert audit["status"] == "skipped"
    assert (tmp_path / "fixtures.csv").exists()
    assert (tmp_path / "absences.csv").exists()
    assert (tmp_path / "realtime_lineups.csv").exists()
    assert pd.read_csv(tmp_path / "absences.csv").empty
