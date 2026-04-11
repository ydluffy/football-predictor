from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from config.settings import ensure_project_dirs, get_settings
from research_director.model_registry import get_current_production_model


class ExecutionRecord(BaseModel):
    run_id: str
    workflow_name: str
    started_at: datetime
    finished_at: datetime
    status: str
    agents_called: list[str] = Field(default_factory=list)
    key_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    metrics_summary: dict[str, Any] = Field(default_factory=dict)
    decision_result: dict[str, Any] | None = None
    model_artifact_status: str | None = None
    model_load_error: str | None = None
    fallback_used: bool | None = None
    fallback_policy: str | None = None

    model_config = {"extra": "ignore"}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def build_execution_record(*, workflow_result: dict[str, Any], started_at: datetime | None = None, finished_at: datetime | None = None) -> ExecutionRecord:
    rid = str(workflow_result.get("run_id") or "")
    workflow_name = str(workflow_result.get("workflow_name") or workflow_result.get("workflow") or "")
    st = str(workflow_result.get("status") or "unknown")

    steps = workflow_result.get("steps") or []
    agents_called: list[str] = []
    key_artifacts: list[dict[str, Any]] = []
    metrics_summary: dict[str, Any] = {}

    for step in steps:
        if not isinstance(step, dict):
            continue
        agent = step.get("agent")
        if agent:
            agents_called.append(str(agent))
        for a in step.get("artifacts") or []:
            if isinstance(a, dict) and a.get("path"):
                key_artifacts.append(
                    {
                        "name": str(a.get("name") or ""),
                        "path": str(a.get("path") or ""),
                        "artifact_type": str(a.get("artifact_type") or ""),
                    }
                )
        m = step.get("metrics")
        if isinstance(m, dict):
            for k, v in m.items():
                if k not in metrics_summary:
                    metrics_summary[k] = v
            if str(step.get("step_key") or "") == "predict" or str(agent) == "predictor":
                if "model_artifact_status" in m:
                    metrics_summary.setdefault("model_artifact_status", m.get("model_artifact_status"))
                if "model_load_error" in m:
                    metrics_summary.setdefault("model_load_error", m.get("model_load_error"))
                if "fallback_used" in m:
                    metrics_summary.setdefault("fallback_used", m.get("fallback_used"))
                if "fallback_policy" in m:
                    metrics_summary.setdefault("fallback_policy", m.get("fallback_policy"))

    for k in ("report_path", "metrics_path", "results_path", "model_path"):
        if workflow_result.get(k):
            key_artifacts.append({"name": k, "path": str(workflow_result.get(k)), "artifact_type": ""})

    return ExecutionRecord(
        run_id=rid,
        workflow_name=workflow_name,
        started_at=started_at or _now_utc(),
        finished_at=finished_at or _now_utc(),
        status=st,
        agents_called=agents_called,
        key_artifacts=key_artifacts,
        metrics_summary=metrics_summary,
        decision_result=workflow_result.get("decision") if isinstance(workflow_result.get("decision"), dict) else None,
        model_artifact_status=metrics_summary.get("model_artifact_status"),
        model_load_error=metrics_summary.get("model_load_error"),
        fallback_used=metrics_summary.get("fallback_used"),
        fallback_policy=metrics_summary.get("fallback_policy"),
    )


def append_execution_record(record: ExecutionRecord) -> None:
    ensure_project_dirs()
    s = get_settings()
    path = s.research_execution_history_path
    path.parent.mkdir(parents=True, exist_ok=True)
    line = record.model_dump_json() + "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def write_latest_execution_summary(record: ExecutionRecord) -> None:
    ensure_project_dirs()
    s = get_settings()
    path = s.research_latest_execution_summary_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")


def _load_run_manifest(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "run_manifest.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_run_manifest(run_dir: Path, payload: dict[str, Any]) -> None:
    path = run_dir / "run_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _model_to_manifest(model: Any) -> dict[str, Any] | None:
    if model is None:
        return None
    if isinstance(model, dict):
        return model
    if hasattr(model, "model_dump"):
        try:
            return model.model_dump(mode="json")
        except Exception:
            return None
    return None


def _extract_input_data_paths(*, manifest: dict[str, Any], workflow_result: dict[str, Any]) -> dict[str, Any]:
    ctx = manifest.get("context") if isinstance(manifest.get("context"), dict) else {}
    paths: dict[str, Any] = {
        "raw_matches_csv": ctx.get("raw_matches_csv"),
        "mapping_path": ctx.get("mapping_path"),
        "today_matches_path": ctx.get("today_matches_path"),
        "matches_path": ctx.get("matches_path"),
        "standardized_data_path": None,
        "import_summary_path": None,
        "validation_path": None,
        "missing_report_path": None,
    }
    metrics = workflow_result.get("metrics") if isinstance(workflow_result.get("metrics"), dict) else {}
    steps = metrics.get("steps") if isinstance(metrics.get("steps"), dict) else {}
    data_m = steps.get("data") if isinstance(steps.get("data"), dict) else {}
    for k in ("standardized_data_path", "import_summary_path", "validation_path", "missing_report_path"):
        if k in data_m:
            paths[k] = data_m.get(k)
    return paths


def _enhance_run_manifest(*, workflow_result: dict[str, Any]) -> None:
    run_dir_raw = workflow_result.get("run_dir")
    if not run_dir_raw:
        return
    run_dir = Path(str(run_dir_raw))
    manifest = _load_run_manifest(run_dir)
    if not manifest:
        return

    ctx = manifest.get("context") if isinstance(manifest.get("context"), dict) else {}
    exec_ctx = manifest.get("execution_context") if isinstance(manifest.get("execution_context"), dict) else {}

    input_data_mode = str(ctx.get("data_mode") or ctx.get("input_data_mode") or "mock")
    input_data_paths = _extract_input_data_paths(manifest=manifest, workflow_result=workflow_result)

    scheduler_triggered = bool(ctx.get("scheduler_triggered")) or str(exec_ctx.get("trigger_mode") or "").lower() == "scheduler"

    registered_before = None
    registered_after = None
    promoted_candidate_id = None

    upgrade_report = run_dir / "upgrade_report.json"
    if upgrade_report.exists():
        try:
            up = json.loads(upgrade_report.read_text(encoding="utf-8"))
        except Exception:
            up = {}
        if isinstance(up, dict):
            registered_before = up.get("production_before")
            registered_after = up.get("current_production_model")
            cand = up.get("new_candidate_model")
            dec = up.get("decision") if isinstance(up.get("decision"), dict) else {}
            if isinstance(cand, dict) and dec.get("decision") == "promote_candidate":
                promoted_candidate_id = cand.get("model_id")
            if promoted_candidate_id is None and isinstance(registered_after, dict) and dec.get("decision") == "promote_candidate":
                promoted_candidate_id = registered_after.get("model_id")

    if registered_after is None:
        prod = get_current_production_model()
        registered_after = _model_to_manifest(prod)
        registered_before = registered_before or registered_after

    manifest["input_data_mode"] = input_data_mode
    manifest["input_data_paths"] = input_data_paths
    manifest["registered_model_before"] = _model_to_manifest(registered_before)
    manifest["registered_model_after"] = _model_to_manifest(registered_after)
    manifest["promoted_candidate_id"] = promoted_candidate_id
    manifest["scheduler_triggered"] = scheduler_triggered

    metrics = workflow_result.get("metrics") if isinstance(workflow_result.get("metrics"), dict) else {}
    steps_m = metrics.get("steps") if isinstance(metrics.get("steps"), dict) else {}
    predict_m = steps_m.get("predict") if isinstance(steps_m.get("predict"), dict) else {}
    manifest["model_artifact_status"] = predict_m.get("model_artifact_status") if predict_m else None
    manifest["model_load_error"] = predict_m.get("model_load_error") if predict_m else None
    manifest["fallback_used"] = predict_m.get("fallback_used") if predict_m else None
    if predict_m and predict_m.get("fallback_policy") is not None:
        manifest["fallback_policy"] = predict_m.get("fallback_policy")
    elif ctx.get("fallback_policy") is not None:
        manifest["fallback_policy"] = str(ctx.get("fallback_policy"))
    else:
        manifest["fallback_policy"] = "graceful" if str(manifest.get("workflow") or "") == "daily_prediction" else None

    _save_run_manifest(run_dir, manifest)


def persist_execution_logs(*, workflow_result: dict[str, Any], started_at: datetime | None = None, finished_at: datetime | None = None) -> ExecutionRecord:
    rec = build_execution_record(workflow_result=workflow_result, started_at=started_at, finished_at=finished_at)
    append_execution_record(rec)
    write_latest_execution_summary(rec)
    _enhance_run_manifest(workflow_result=workflow_result)
    return rec
