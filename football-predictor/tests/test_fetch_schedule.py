from __future__ import annotations

from ingest.fetch_schedule import FootballDataClient


def test_mock_schedule_requires_explicit_opt_in(monkeypatch):
    class FailedResponse:
        status_code = 500

        def json(self):
            return {}

    monkeypatch.setattr("ingest.fetch_schedule.requests.get", lambda *args, **kwargs: FailedResponse())

    real_mode = FootballDataClient(allow_mock=False)._fetch_from_public_fallback("2025-01-01")
    mock_mode = FootballDataClient(allow_mock=True)._fetch_from_public_fallback("2025-01-01")

    assert real_mode.empty
    assert not mock_mode.empty
