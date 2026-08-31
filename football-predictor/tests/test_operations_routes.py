from __future__ import annotations

from fastapi import Response

from api.routes.operations import RunExperimentRequest, _readiness_payload, build_operations_router


def _endpoints() -> dict[str, object]:
    router = build_operations_router(
        model_status=lambda: {
            "model_loaded": True,
            "model_path": "model.pkl",
            "data": {"quality_status": "pass"},
        },
        artifacts=lambda: {"artifact": "ready"},
        analyze=lambda: {"analysis": "ready"},
        explain_high_brier=lambda: {"reason": "calibration"},
        run_experiment=lambda command: {"command": command},
        system_status=lambda: {"status": "ready"},
        runtime_metrics=lambda: {"requests_total": 3},
    )
    return {
        route.path: route.endpoint
        for route in router.routes
        if hasattr(route, "path") and hasattr(route, "endpoint")
    }


def test_health_route_reports_model_status() -> None:
    health = _endpoints()["/health"]

    payload = health()

    assert payload["ok"] is True
    assert payload["ready"] is True
    assert payload["status"] == "healthy"
    assert payload["model_path"] == "model.pkl"
    assert payload["requests"] == {"requests_total": 3}


def test_liveness_readiness_and_metrics_routes() -> None:
    endpoints = _endpoints()

    assert endpoints["/health/live"]() == {"ok": True, "status": "alive"}
    response = Response()
    assert endpoints["/health/ready"](response)["ready"] is True
    assert response.status_code == 200
    assert endpoints["/metrics"]() == {"requests_total": 3}


def test_readiness_returns_503_when_data_quality_failed() -> None:
    response = Response()

    payload = _readiness_payload(
        response,
        lambda: {"model_loaded": True, "data": {"quality_status": "fail"}},
        lambda: {},
    )

    assert payload["ready"] is False
    assert payload["status"] == "unhealthy"
    assert response.status_code == 503


def test_copilot_routes_delegate_to_services() -> None:
    endpoints = _endpoints()

    assert endpoints["/copilot/artifacts"]() == {"artifact": "ready"}
    assert endpoints["/copilot/analyze"]() == {"analysis": "ready"}
    assert endpoints["/copilot/explain-high-brier"]() == {"reason": "calibration"}
    assert endpoints["/copilot/run"](RunExperimentRequest(command_text="logit v3")) == {
        "command": "logit v3"
    }
    assert endpoints["/copilot/status"]() == {"status": "ready"}
