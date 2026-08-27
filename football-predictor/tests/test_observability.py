from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.observability import (
    ObservabilityMiddleware,
    RequestMetricsRegistry,
    data_runtime_metadata,
    get_request_id,
    model_runtime_metadata,
)


def _app() -> tuple[FastAPI, RequestMetricsRegistry]:
    app = FastAPI()
    registry = RequestMetricsRegistry()
    app.add_middleware(ObservabilityMiddleware, registry=registry)

    @app.get("/ok")
    def ok() -> dict[str, object]:
        return {"request_id": get_request_id()}

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    return app, registry


def test_middleware_propagates_request_id_and_records_latency() -> None:
    app, registry = _app()

    with TestClient(app) as client:
        response = client.get("/ok", headers={"X-Request-ID": "trace-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-123"
    assert float(response.headers["X-Response-Time-Ms"]) >= 0.0
    assert response.json() == {"request_id": "trace-123"}
    metrics = registry.snapshot()
    assert metrics["requests_total"] == 1
    assert metrics["responses_total"] == 1
    assert metrics["server_errors_total"] == 0


def test_middleware_generates_safe_id_and_sanitizes_unhandled_errors() -> None:
    app, registry = _app()

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom", headers={"X-Request-ID": "invalid id with spaces"})

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] != "invalid id with spaces"
    assert response.json()["detail"] == "internal server error"
    assert "secret internal detail" not in response.text
    assert registry.snapshot()["server_errors_total"] == 1


def test_runtime_metadata_reads_model_manifest_and_quality_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_path = tmp_path / "model.pkl"
    model_path.write_bytes(b"model")
    model_path.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "artifact_sha256": "abcdef1234567890",
                "model_type": "logit",
                "feature_version": "v3",
                "created_at": "2026-08-28T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    report_path = tmp_path / "quality.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "pass",
                "as_of_utc": "2026-08-28T01:00:00Z",
                "generated_at_utc": "2026-08-28T01:01:00Z",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("MODEL_VERSION", raising=False)
    monkeypatch.delenv("DATA_SNAPSHOT_VERSION", raising=False)

    model = model_runtime_metadata(model_path)
    data = data_runtime_metadata(report_path)

    assert model["version"] == "abcdef123456"
    assert model["manifest_status"] == "available"
    assert data["snapshot_version"] == "2026-08-28T01:00:00Z"
    assert data["quality_status"] == "pass"
