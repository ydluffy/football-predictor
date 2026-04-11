from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from research_director.report_writer import write_daily_report


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


def run_daily_prediction_workflow(
    *,
    ctx: dict[str, Any],
    run_dir: Path,
    run_step: Callable[[str, str, str, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []

    data_mode = str(ctx.get("data_mode") or "mock")
    if not ctx.get("fallback_policy"):
        ctx["fallback_policy"] = "graceful"
    if data_mode == "real":
        raw_matches_csv = ctx.get("raw_matches_csv")
        mapping_path = ctx.get("mapping_path")
        if not raw_matches_csv or not mapping_path:
            artifacts, metrics = _aggregate(steps)
            decision = {"decision": "review_required", "reason": "real_mode_requires_raw_and_mapping", "details": {"raw_matches_csv": bool(raw_matches_csv), "mapping_path": bool(mapping_path)}}
            return {"status": "review_required", "steps": steps, "artifacts": artifacts, "metrics": metrics, "decision": decision, "error_message": "data_mode=real 需要 raw_matches_csv + mapping_path"}

    today_matches_path = ctx.get("today_matches_path")
    if today_matches_path:
        p = Path(str(today_matches_path))
        if p.exists():
            ctx["today_matches_path"] = str(p)
    else:
        today_default = run_dir / "daily_matches.csv"
        if today_default.exists():
            ctx["today_matches_path"] = str(today_default)

    if data_mode == "real" or not ctx.get("today_matches_path"):
        data_step = run_step("data", "data_scout", "low", ctx)
        steps.append(data_step)
        if data_step.get("status") != "completed":
            artifacts, metrics = _aggregate(steps)
            err = ""
            if isinstance(data_step.get("metrics"), dict):
                err = str((data_step["metrics"].get("error_message") or ""))
            decision = {"decision": "review_required", "reason": "data_import_failed", "details": {"step_status": data_step.get("status"), "summary": data_step.get("summary"), "error_message": err}}
            return {"status": "review_required", "steps": steps, "artifacts": artifacts, "metrics": metrics, "decision": decision, "error_message": err or str(data_step.get("summary") or "")}
        for a in data_step.get("artifacts", []):
            if a.get("name") == "today_matches_csv":
                ctx["today_matches_path"] = a.get("path")
        if isinstance(data_step.get("metrics"), dict) and data_step["metrics"].get("standardized_data_path"):
            ctx["today_matches_path"] = str(data_step["metrics"]["standardized_data_path"])
            ctx["standardized_data_path"] = str(data_step["metrics"]["standardized_data_path"])

    feat_step = run_step("features", "feature_lab", "low", ctx)
    steps.append(feat_step)
    if feat_step.get("status") != "completed":
        artifacts, metrics = _aggregate(steps)
        return {"status": str(feat_step.get("status") or "failed"), "steps": steps, "artifacts": artifacts, "metrics": metrics, "decision": None}

    pred_step = run_step("predict", "predictor", "medium", ctx)
    steps.append(pred_step)
    if pred_step.get("status") != "completed":
        artifacts, metrics = _aggregate(steps)
        return {"status": str(pred_step.get("status") or "failed"), "steps": steps, "artifacts": artifacts, "metrics": metrics, "decision": None}

    use_verifier = bool(ctx.get("use_verifier", True))
    verifier_path = None
    if use_verifier:
        ctx2 = dict(ctx)
        for a in pred_step.get("artifacts", []):
            if a.get("name") == "daily_predictions":
                ctx2["predictions_path"] = a.get("path")
        ver_step = run_step("verify", "verifier", "low", ctx2)
        steps.append(ver_step)
        if ver_step.get("status") != "completed":
            artifacts, metrics = _aggregate(steps)
            return {"status": str(ver_step.get("status") or "failed"), "steps": steps, "artifacts": artifacts, "metrics": metrics, "decision": None}
        for a in ver_step.get("artifacts", []):
            if a.get("name") == "daily_verifier_results":
                verifier_path = a.get("path")

    predictions_path = None
    for a in pred_step.get("artifacts", []):
        if a.get("name") == "daily_predictions":
            predictions_path = a.get("path")
    report_path = write_daily_report(
        run_dir,
        predictions_path=Path(str(predictions_path)) if predictions_path else (run_dir / "daily_predictions.csv"),
        verifier_path=Path(str(verifier_path)) if verifier_path else None,
    )

    artifacts, metrics = _aggregate(steps)
    artifacts.append({"name": "daily_report", "path": str(report_path), "artifact_type": "json"})
    return {"status": "completed", "steps": steps, "artifacts": artifacts, "metrics": metrics, "decision": None}
