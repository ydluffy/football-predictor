from __future__ import annotations

import json
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import ensure_project_dirs, get_settings
from research_director.execution_context import ExecutionContext
from research_director.execution_log import persist_execution_logs
from research_director.retry_policy import classify_exception, get_retry_delay, should_retry
from research_director.state_store import ResearchStateStore
from research_director.task_router import TaskRouter
from research_director.workflows.candidate_model_upgrade_workflow import run_candidate_model_upgrade_workflow
from research_director.workflows.daily_prediction_workflow import run_daily_prediction_workflow
from research_director.workflows.post_match_learning_workflow import run_post_match_learning_workflow


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    try:
        import pandas as pd  # type: ignore

        if isinstance(value, pd.DataFrame):
            return {"__type__": "DataFrame", "shape": [int(value.shape[0]), int(value.shape[1])]}
    except Exception:
        pass
    return {"__type__": type(value).__name__, "repr": str(value)[:200]}


@dataclass(frozen=True)
class Gate:
    allow_high_risk: bool = False

    def allow(self, *, risk_level: str, context: dict[str, Any]) -> tuple[bool, str]:
        r = str(risk_level)
        if r != "high":
            return True, "allowed"
        if not self.allow_high_risk:
            return False, "blocked_high_risk"
        if context.get("data_quality_ok") is False:
            return False, "blocked_data_quality_failed"
        if context.get("pytest_passed") is False:
            return False, "blocked_pytest_failed"
        return True, "allowed"


class ResearchDirector:
    def __init__(self, *, store: ResearchStateStore | None = None, gate: Gate | None = None, router: TaskRouter | None = None) -> None:
        ensure_project_dirs()
        self._store = store or ResearchStateStore()
        self._gate = gate or Gate(allow_high_risk=False)
        self._router = router or TaskRouter()

    @property
    def store(self) -> ResearchStateStore:
        return self._store

    def run(
        self,
        workflow: str,
        *,
        context: dict[str, Any] | None = None,
        run_id: str | None = None,
        resume: bool = False,
    ) -> dict[str, Any]:
        started_at = datetime.now(timezone.utc)
        ctx = dict(context or {})
        rid = str(run_id or ctx.get("run_id") or uuid.uuid4())
        ctx["run_id"] = rid
        ctx.setdefault("allow_high_risk", bool(self._gate.allow_high_risk))
        ctx.setdefault("data_mode", "mock")
        ensure_project_dirs()
        s = get_settings()
        run_dir = s.research_director_runs_dir / rid
        run_dir.mkdir(parents=True, exist_ok=True)
        ctx["run_dir"] = str(run_dir)

        exec_ctx = ExecutionContext(
            run_id=rid,
            workflow_name=str(workflow),
            trigger_mode=str(ctx.get("trigger_mode") or "manual"),
            status="running",
            model_type=ctx.get("model_type"),
            feature_version=ctx.get("feature_version"),
            calibration_method=ctx.get("calibration_method") or ctx.get("calibration"),
            use_verifier=bool(ctx.get("use_verifier", False)),
            input_paths={str(k): str(v) for k, v in (ctx.get("input_paths") or {}).items()} if isinstance(ctx.get("input_paths"), dict) else {},
            output_paths={str(k): str(v) for k, v in (ctx.get("output_paths") or {}).items()} if isinstance(ctx.get("output_paths"), dict) else {},
            notes={},
        )
        ctx["execution_context"] = exec_ctx.to_dict()

        manifest_path = run_dir / "run_manifest.json"
        payload: dict[str, Any] = {"status": "failed", "steps": [], "error_message": None}
        try:
            self._store.create_run(run_id=rid, workflow=workflow)
            if not manifest_path.exists() or not resume:
                manifest_path.write_text(
                    json.dumps(
                        {
                            "run_id": rid,
                            "workflow": str(workflow),
                            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                            "resume": bool(resume),
                            "context": _jsonable(ctx),
                            "execution_context": exec_ctx.to_dict(),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

            if workflow == "daily_prediction":
                payload = run_daily_prediction_workflow(
                    ctx=ctx,
                    run_dir=run_dir,
                    run_step=lambda step_key, agent_name, risk_level, ctx_in: self._run_step(
                        workflow="daily_prediction",
                        step_key=step_key,
                        agent_name=agent_name,
                        risk_level=risk_level,
                        ctx=ctx_in,
                        run_dir=run_dir,
                        resume=resume,
                    ),
                )
            elif workflow == "post_match_learning":
                payload = run_post_match_learning_workflow(
                    ctx=ctx,
                    run_dir=run_dir,
                    run_step=lambda step_key, agent_name, risk_level, ctx_in: self._run_step(
                        workflow="post_match_learning",
                        step_key=step_key,
                        agent_name=agent_name,
                        risk_level=risk_level,
                        ctx=ctx_in,
                        run_dir=run_dir,
                        resume=resume,
                    ),
                )
            elif workflow == "candidate_model_upgrade":
                payload = run_candidate_model_upgrade_workflow(
                    ctx=ctx,
                    run_dir=run_dir,
                    run_step=lambda step_key, agent_name, risk_level, ctx_in: self._run_step(
                        workflow="candidate_model_upgrade",
                        step_key=step_key,
                        agent_name=agent_name,
                        risk_level=risk_level,
                        ctx=ctx_in,
                        run_dir=run_dir,
                        resume=resume,
                    ),
                )
            else:
                raise ValueError("workflow 仅支持 daily_prediction/post_match_learning/candidate_model_upgrade")
        except Exception as e:
            payload = {"status": "failed", "steps": [], "error_message": str(e)}
        finally:
            finished_at = datetime.now(timezone.utc)
            payload["run_id"] = rid
            payload["run_dir"] = str(run_dir)
            payload["workflow_name"] = str(workflow)

            final_status = str(payload.get("status") or "completed")
            self._store.set_run_status(run_id=rid, status=final_status)

            try:
                final_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"run_id": rid, "workflow": str(workflow)}
            except Exception:
                final_manifest = {"run_id": rid, "workflow": str(workflow)}
            final_manifest["status"] = final_status
            final_manifest["finished_at"] = finished_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            exec_ctx.finish(status=final_status, error_message=payload.get("error_message"), finished_at=finished_at)
            final_manifest["execution_context"] = exec_ctx.to_dict()
            manifest_path.write_text(json.dumps(final_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            persist_execution_logs(workflow_result=payload, started_at=exec_ctx.started_at, finished_at=exec_ctx.finished_at)

        return payload

    def _run_step(
        self,
        *,
        workflow: str,
        step_key: str,
        agent_name: str,
        risk_level: str,
        ctx: dict[str, Any],
        run_dir: Path,
        resume: bool,
    ) -> dict[str, Any]:
        agent = self._router.get(agent_name)
        if agent is None:
            raise ValueError(f"未知 agent: {agent_name}")

        step_dir = run_dir / "steps" / str(step_key)
        step_dir.mkdir(parents=True, exist_ok=True)
        record_path = step_dir / "step_result.json"
        if resume and record_path.exists():
            try:
                return json.loads(record_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        max_retries = int(ctx.get("max_retries") or 0)
        allowed, reason = self._gate.allow(risk_level=risk_level, context=ctx)
        for attempt in range(1, max_retries + 2):
            step_id = f"{ctx['run_id']}:{step_key}:{attempt}"
            step_ctx = dict(ctx)
            step_ctx["step_key"] = str(step_key)
            step_ctx["attempt"] = int(attempt)
            step_ctx["run_dir"] = str(run_dir)
            step_ctx["step_dir"] = str(step_dir)

            self._store.add_step(run_id=ctx["run_id"], step_id=step_id, agent=agent_name, workflow=workflow, status="planned", params=step_ctx)
            started = datetime.now(timezone.utc)
            self._store.update_step(step_id=step_id, status="running", started_at=started, attempt=attempt)

            if not allowed:
                finished = datetime.now(timezone.utc)
                payload = {
                    "step_id": step_id,
                    "step_key": str(step_key),
                    "agent": agent_name,
                    "status": "blocked",
                    "summary": reason,
                    "attempt": int(attempt),
                    "artifacts": [],
                    "metrics": {},
                }
                self._store.update_step(step_id=step_id, status="blocked", finished_at=finished, summary=reason, attempt=attempt)
                (step_dir / f"step_result_attempt_{attempt}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                record_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                return payload

            try:
                plan = agent.plan(context=step_ctx)
                res = agent.execute(context={**step_ctx, **plan}, gate=self._gate)
                self._store.update_step(step_id=step_id, status=res.status, finished_at=res.finished_at, summary=res.summary, attempt=attempt)
                for a in res.artifacts:
                    self._store.add_artifact(step_id=step_id, name=a.name, path=a.path, artifact_type=a.artifact_type, metadata=a.metadata)

                payload = {
                    "step_id": step_id,
                    "step_key": str(step_key),
                    "agent": agent_name,
                    "status": res.status,
                    "summary": agent.summarize(res),
                    "attempt": int(attempt),
                    "artifacts": [a.__dict__ for a in res.artifacts],
                    "metrics": res.metrics,
                }
                (step_dir / f"step_result_attempt_{attempt}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                record_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                return payload
            except Exception as e:
                finished = datetime.now(timezone.utc)
                category = classify_exception(e)
                err = {"type": str(category), "message": str(e), "traceback": traceback.format_exc()}
                retryable = bool(should_retry(str(category)))
                will_retry = bool(retryable and attempt < max_retries + 1)
                delay = int(get_retry_delay(attempt + 1)) if will_retry else 0

                status = "retrying" if will_retry else "failed"
                summary = "retrying" if will_retry else "failed"
                payload = {
                    "step_id": step_id,
                    "step_key": str(step_key),
                    "agent": agent_name,
                    "status": status,
                    "summary": summary,
                    "attempt": int(attempt),
                    "retryable": bool(retryable),
                    "retry_delay_sec": int(delay),
                    "artifacts": [],
                    "metrics": {},
                    "error": err,
                }
                self._store.update_step(step_id=step_id, status=status, finished_at=finished, summary=str(e), error=err, attempt=attempt)
                (step_dir / f"step_result_attempt_{attempt}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                record_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                if not will_retry:
                    return payload
        return {"step_id": None, "step_key": str(step_key), "agent": agent_name, "status": "failed", "summary": "retry_exhausted", "artifacts": [], "metrics": {}}

    def _run_daily(self, ctx: dict[str, Any], run_dir: Path, *, resume: bool) -> dict[str, Any]:
        return run_daily_prediction_workflow(
            ctx=ctx,
            run_dir=run_dir,
            run_step=lambda step_key, agent_name, risk_level, ctx_in: self._run_step(
                workflow="daily_prediction",
                step_key=step_key,
                agent_name=agent_name,
                risk_level=risk_level,
                ctx=ctx_in,
                run_dir=run_dir,
                resume=resume,
            ),
        )

    def _run_post_match(self, ctx: dict[str, Any], run_dir: Path, *, resume: bool) -> dict[str, Any]:
        return run_post_match_learning_workflow(
            ctx=ctx,
            run_dir=run_dir,
            run_step=lambda step_key, agent_name, risk_level, ctx_in: self._run_step(
                workflow="post_match_learning",
                step_key=step_key,
                agent_name=agent_name,
                risk_level=risk_level,
                ctx=ctx_in,
                run_dir=run_dir,
                resume=resume,
            ),
        )

    def _run_upgrade(self, ctx: dict[str, Any], run_dir: Path, *, resume: bool) -> dict[str, Any]:
        return run_candidate_model_upgrade_workflow(
            ctx=ctx,
            run_dir=run_dir,
            run_step=lambda step_key, agent_name, risk_level, ctx_in: self._run_step(
                workflow="candidate_model_upgrade",
                step_key=step_key,
                agent_name=agent_name,
                risk_level=risk_level,
                ctx=ctx_in,
                run_dir=run_dir,
                resume=resume,
            ),
        )
