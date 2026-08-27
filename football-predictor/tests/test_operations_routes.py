from __future__ import annotations

from fastapi import FastAPI

from api.routes.operations import RunExperimentRequest, build_operations_router


def _endpoints() -> dict[str, object]:
    app = FastAPI()
    app.include_router(
        build_operations_router(
            model_status=lambda: {"model_loaded": True, "model_path": "model.pkl"},
            artifacts=lambda: {"artifact": "ready"},
            analyze=lambda: {"analysis": "ready"},
            explain_high_brier=lambda: {"reason": "calibration"},
            run_experiment=lambda command: {"command": command},
            system_status=lambda: {"status": "ready"},
        )
    )
    return {route.path: route.endpoint for route in app.routes}


def test_health_route_reports_model_status() -> None:
    health = _endpoints()["/health"]

    assert health() == {
        "ok": True,
        "model_loaded": True,
        "model_path": "model.pkl",
    }


def test_copilot_routes_delegate_to_services() -> None:
    endpoints = _endpoints()

    assert endpoints["/copilot/artifacts"]() == {"artifact": "ready"}
    assert endpoints["/copilot/analyze"]() == {"analysis": "ready"}
    assert endpoints["/copilot/explain-high-brier"]() == {"reason": "calibration"}
    assert endpoints["/copilot/run"](RunExperimentRequest(command_text="logit v3")) == {
        "command": "logit v3"
    }
    assert endpoints["/copilot/status"]() == {"status": "ready"}
