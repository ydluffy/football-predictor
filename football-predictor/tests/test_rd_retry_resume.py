from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import get_settings
from research_director.agents.agent_base import StepArtifact, StepResult
from research_director.director import ResearchDirector


class _FailOnceEvaluator:
    name = "evaluator"

    def plan(self, *, context: dict[str, Any]) -> dict[str, Any]:
        return {}

    def execute(self, *, context: dict[str, Any], gate: Any) -> StepResult:
        attempt = int(context.get("attempt") or 1)
        if attempt == 1:
            raise RuntimeError("boom")

        run_dir = Path(str(context["run_dir"]))
        run_dir.mkdir(parents=True, exist_ok=True)
        out_path = run_dir / "post_match_results_proxy.csv"
        out_path.write_text("match_id,p_home,p_draw,p_away,actual\nm1,0.3,0.3,0.4,H\n", encoding="utf-8")

        now = datetime.now(timezone.utc)
        return StepResult(
            status="completed",
            summary="ok",
            started_at=now,
            finished_at=now,
            artifacts=[StepArtifact(name="post_match_results_proxy", path=str(out_path), artifact_type="csv", metadata={})],
            metrics={"brier": 0.1, "logloss": 0.2},
        )

    def summarize(self, result: StepResult) -> str:
        return result.summary


class _NoopOptimizer:
    name = "optimizer"

    def plan(self, *, context: dict[str, Any]) -> dict[str, Any]:
        return {}

    def execute(self, *, context: dict[str, Any], gate: Any) -> StepResult:
        run_dir = Path(str(context["run_dir"]))
        run_dir.mkdir(parents=True, exist_ok=True)
        out_path = run_dir / "optimizer_suggestions.json"
        out_path.write_text(json.dumps({"suggestions": []}), encoding="utf-8")

        now = datetime.now(timezone.utc)
        return StepResult(
            status="completed",
            summary="ok",
            started_at=now,
            finished_at=now,
            artifacts=[StepArtifact(name="optimizer_suggestions", path=str(out_path), artifact_type="json", metadata={})],
            metrics={},
        )

    def summarize(self, result: StepResult) -> str:
        return result.summary


class _Router:
    def __init__(self, agents: dict[str, Any]) -> None:
        self._agents = agents

    def get(self, agent_name: str):
        return self._agents.get(str(agent_name))


def test_director_retries_failed_step_and_records_step_result(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    router = _Router({"evaluator": _FailOnceEvaluator(), "optimizer": _NoopOptimizer()})
    director = ResearchDirector(router=router)
    out = director.run("post_match_learning", context={"max_retries": 1})
    run_dir = Path(out["run_dir"])

    step_record = json.loads((run_dir / "steps" / "evaluate" / "step_result.json").read_text(encoding="utf-8"))
    assert step_record["status"] == "completed"
    assert step_record["attempt"] == 2
    assert (run_dir / "run_manifest.json").exists()


def test_director_resume_skips_step_execution(monkeypatch, tmp_path):
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    router_ok = _Router({"evaluator": _FailOnceEvaluator(), "optimizer": _NoopOptimizer()})
    director_ok = ResearchDirector(router=router_ok)
    first = director_ok.run("post_match_learning", context={"max_retries": 1})
    run_id = first["run_id"]

    class _AlwaysFail:
        name = "evaluator"

        def plan(self, *, context: dict[str, Any]) -> dict[str, Any]:
            return {}

        def execute(self, *, context: dict[str, Any], gate: Any) -> StepResult:
            raise RuntimeError("should_not_run")

        def summarize(self, result: StepResult) -> str:
            return result.summary

    router_fail = _Router({"evaluator": _AlwaysFail(), "optimizer": _NoopOptimizer()})
    director_resume = ResearchDirector(router=router_fail)
    second = director_resume.run("post_match_learning", context={}, run_id=run_id, resume=True)
    assert second["run_id"] == run_id
    assert second["status"] == "completed"

