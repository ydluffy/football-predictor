from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from research_director.report_writer import write_post_match_report


def _aggregate(steps: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    metrics_by_step: dict[str, Any] = {}
    for st in steps:
        if not isinstance(st, dict):
            continue
        key = str(st.get("step_key") or st.get("agent") or "")
        if key and isinstance(st.get("metrics"), dict):
            metrics_by_step[key] = st["metrics"]
        for a in st.get("artifacts") or []:
            if isinstance(a, dict) and a.get("path"):
                artifacts.append(a)
    return artifacts, {"steps": metrics_by_step}


def run_post_match_learning_workflow(
    *,
    ctx: dict[str, Any],
    run_dir: Path,
    run_step: Callable[[str, str, str, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []

    needs_ingest = bool(ctx.get("raw_matches_csv") or ctx.get("data_sources"))
    if needs_ingest:
        ctx2 = dict(ctx)
        ctx2["keep_actual_result"] = True
        ctx2["output_csv_path"] = str(run_dir / "real_matches_standardized.csv")
        data_step = run_step("data", "data_scout", "low", ctx2)
        steps.append(data_step)
        if data_step.get("status") != "completed":
            artifacts, metrics = _aggregate(steps)
            return {"status": str(data_step.get("status") or "failed"), "steps": steps, "artifacts": artifacts, "metrics": metrics, "decision": None, "error_message": str(data_step.get("summary") or "")}
        for a in data_step.get("artifacts", []):
            if a.get("name") == "matches_standardized_csv":
                ctx["matches_path"] = a.get("path")

    matches_path = ctx.get("matches_path")
    if matches_path:
        p = Path(str(matches_path))
        if not p.exists():
            artifacts, metrics = _aggregate(steps)
            return {"status": "failed", "steps": steps, "artifacts": artifacts, "metrics": metrics, "decision": None, "error_message": "matches_path_not_found"}
    else:
        ctx["matches_path"] = str(Path(ctx["run_dir"]).parent / "data" / "processed" / "real_matches_standardized.csv")

    ev = run_step("evaluate", "evaluator", "medium", ctx)
    steps.append(ev)
    if ev.get("status") != "completed":
        artifacts, metrics = _aggregate(steps)
        return {"status": str(ev.get("status") or "failed"), "steps": steps, "artifacts": artifacts, "metrics": metrics, "decision": None, "error_message": str(ev.get("summary") or "")}

    opt = run_step("optimize", "optimizer", "low", ctx)
    steps.append(opt)

    metrics_out: dict[str, Any] = dict(ev.get("metrics") or {})
    error_path = run_dir / "error_analysis_with_risk.csv"
    report_path = write_post_match_report(run_dir, metrics=metrics_out, error_analysis_path=error_path if error_path.exists() else None)

    artifacts, metrics = _aggregate(steps)
    artifacts.append({"name": "post_match_report", "path": str(report_path), "artifact_type": "json"})
    return {"status": "completed", "steps": steps, "artifacts": artifacts, "metrics": metrics, "decision": None}
