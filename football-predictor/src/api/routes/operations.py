from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter
from pydantic import BaseModel


class RunExperimentRequest(BaseModel):
    command_text: str


def build_operations_router(
    *,
    model_status: Callable[[], dict[str, object]],
    artifacts: Callable[[], dict[str, object]],
    analyze: Callable[[], dict[str, object]],
    explain_high_brier: Callable[[], dict[str, object]],
    run_experiment: Callable[[str], dict[str, object]],
    system_status: Callable[[], dict[str, object]],
) -> APIRouter:
    """Build read-mostly operational routes with explicit service dependencies."""

    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, object]:
        return {"ok": True, **model_status()}

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
