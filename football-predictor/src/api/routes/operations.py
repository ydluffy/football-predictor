from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Response
from pydantic import BaseModel


class RunExperimentRequest(BaseModel):
    command_text: str


def _health_payload(
    model_status: Callable[[], dict[str, object]],
    metrics_provider: Callable[[], dict[str, object]],
) -> dict[str, object]:
    details = model_status()
    model_loaded = bool(details.get("model_loaded"))
    data_value = details.get("data")
    data: dict[str, object] = data_value if isinstance(data_value, dict) else {}
    quality_status = data.get("quality_status", "unknown")
    ready = model_loaded and quality_status not in {"fail", "error"}
    if not ready:
        status = "unhealthy"
    elif quality_status == "pass":
        status = "healthy"
    else:
        status = "degraded"
    return {
        "ok": model_loaded,
        "ready": ready,
        "status": status,
        **details,
        "requests": metrics_provider(),
    }


def _readiness_payload(
    response: Response,
    model_status: Callable[[], dict[str, object]],
    metrics_provider: Callable[[], dict[str, object]],
) -> dict[str, object]:
    payload = _health_payload(model_status, metrics_provider)
    response.status_code = 200 if payload["ready"] else 503
    return payload


def build_operations_router(
    *,
    model_status: Callable[[], dict[str, object]],
    artifacts: Callable[[], dict[str, object]],
    analyze: Callable[[], dict[str, object]],
    explain_high_brier: Callable[[], dict[str, object]],
    run_experiment: Callable[[str], dict[str, object]],
    system_status: Callable[[], dict[str, object]],
    runtime_metrics: Callable[[], dict[str, object]] | None = None,
) -> APIRouter:
    """Build read-mostly operational routes with explicit service dependencies."""

    router = APIRouter()

    metrics_provider = runtime_metrics or (lambda: {})

    @router.get("/health")
    def health() -> dict[str, object]:
        return _health_payload(model_status, metrics_provider)

    @router.get("/health/live")
    def liveness() -> dict[str, object]:
        return {"ok": True, "status": "alive"}

    @router.get("/health/ready")
    def readiness(response: Response) -> dict[str, object]:
        return _readiness_payload(response, model_status, metrics_provider)

    @router.get("/metrics")
    def metrics() -> dict[str, object]:
        return metrics_provider()

    @router.get("/copilot/artifacts")
    def copilot_artifacts() -> dict[str, object]:
        return artifacts()

    @router.get("/copilot/analyze")
    def copilot_analyze() -> dict[str, object]:
        return analyze()

    @router.get("/copilot/explain-high-brier")
    def copilot_explain_high_brier() -> dict[str, object]:
        return explain_high_brier()

    @router.post("/copilot/run")
    def copilot_run(req: RunExperimentRequest) -> dict[str, object]:
        return run_experiment(req.command_text)

    @router.get("/copilot/status")
    def copilot_status() -> dict[str, object]:
        return system_status()

    return router
