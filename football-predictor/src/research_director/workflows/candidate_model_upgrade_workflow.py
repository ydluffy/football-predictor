from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from config.settings import get_settings
from research_director.decision_policy import decide_candidate_upgrade
from research_director.model_registry import find_model, get_current_production_model, guess_candidate_artifacts, mark_production, register_candidate, set_candidate_status
from research_director.report_writer import write_upgrade_report


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


def run_candidate_model_upgrade_workflow(
    *,
    ctx: dict[str, Any],
    run_dir: Path,
    run_step: Callable[[str, str, str, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []

    production_before = get_current_production_model()
    allow_high_risk = bool(ctx.get("allow_high_risk", False))

    data_mode = str(ctx.get("data_mode") or "mock")
    needs_ingest = bool(ctx.get("raw_matches_csv") or ctx.get("data_sources"))
    if needs_ingest:
        if data_mode == "real":
            raw_matches_csv = ctx.get("raw_matches_csv")
            mapping_path = ctx.get("mapping_path")
            if not raw_matches_csv or not mapping_path:
                artifacts, metrics = _aggregate(steps)
                decision = {"decision": "review_required", "reason": "real_mode_requires_raw_and_mapping", "details": {"raw_matches_csv": bool(raw_matches_csv), "mapping_path": bool(mapping_path)}}
                return {"status": "review_required", "steps": steps, "artifacts": artifacts, "metrics": metrics, "decision": decision, "error_message": "data_mode=real 需要 raw_matches_csv + mapping_path"}

        ctx2 = dict(ctx)
        ctx2["keep_actual_result"] = True
        ctx2["output_csv_path"] = str(run_dir / "sandbox_project" / "data" / "processed" / "real_matches_standardized.csv")
        data_step = run_step("data", "data_scout", "low", ctx2)
        steps.append(data_step)
        if data_step.get("status") != "completed":
            artifacts, metrics = _aggregate(steps)
            err = ""
            if isinstance(data_step.get("metrics"), dict):
                err = str((data_step["metrics"].get("error_message") or ""))
            decision = {"decision": "review_required", "reason": "data_import_failed", "details": {"step_status": data_step.get("status"), "summary": data_step.get("summary"), "error_message": err}}
            return {"status": "review_required", "steps": steps, "artifacts": artifacts, "metrics": metrics, "decision": decision, "error_message": err or str(data_step.get("summary") or "")}
        std_path = None
        validation_path = None
        if isinstance(data_step.get("metrics"), dict):
            if data_step["metrics"].get("standardized_data_path"):
                std_path = str(data_step["metrics"]["standardized_data_path"])
                ctx["matches_path"] = std_path
            if data_step["metrics"].get("validation_path"):
                validation_path = str(data_step["metrics"]["validation_path"])
            if (data_step["metrics"].get("data_quality_ok") is False) or (isinstance(data_step["metrics"].get("required_fields_missing"), list) and len(data_step["metrics"]["required_fields_missing"]) > 0):
                artifacts, metrics = _aggregate(steps)
                decision = {"decision": "review_required", "gate_reasons": ["data_quality_failed"], "details": {"validation_path": validation_path, "standardized_data_path": std_path}}
                report_path = write_upgrade_report(
                    run_dir,
                    decision=decision,
                    production_model=production_before,
                    candidate_model=None,
                    production_before=production_before,
                    production_after=production_before,
                    allow_high_risk=allow_high_risk,
                    candidate_was_registered=False,
                    standardized_data_path=std_path,
                    validation_path=validation_path,
                )
                artifacts.append({"name": "upgrade_report", "path": str(report_path), "artifact_type": "json"})
                return {"status": "review_required", "steps": steps, "artifacts": artifacts, "metrics": metrics, "decision": decision}

    trainer = run_step("train", "model_trainer", "high", ctx)
    steps.append(trainer)

    s = get_settings()
    current_metrics = dict(ctx.get("current_metrics") or {})
    if not current_metrics and s.eval_metrics_path.exists():
        try:
            current_metrics = json.loads(s.eval_metrics_path.read_text(encoding="utf-8"))
        except Exception:
            current_metrics = {}

    candidate_metrics = dict(ctx.get("candidate_metrics") or {})
    tm = trainer.get("metrics", {}).get("train_metrics")
    if not candidate_metrics and isinstance(tm, dict):
        candidate_metrics = tm

    pytest_passed = bool(ctx.get("pytest_passed", True))
    data_quality_ok = bool(ctx.get("data_quality_ok", True))
    high_conf_delta = int(ctx.get("high_confidence_errors_delta") or 0)

    candidate_entry = None
    candidate_id = None
    candidate_was_registered = False
    if trainer.get("status") == "completed":
        model_type = str(ctx.get("model_type") or "lightgbm")
        model_path, metrics_path = guess_candidate_artifacts(run_dir=run_dir, model_type=model_type)
        artifact_path = str(model_path or "")
        calibration_method = str(ctx.get("calibration") or ctx.get("calibration_method") or "none")
        metrics_summary = dict(candidate_metrics or {})
        if metrics_path:
            metrics_summary["metrics_path"] = str(metrics_path)
        candidate_entry = register_candidate(
            model_type=model_type,
            feature_version=str(ctx.get("feature_version") or ""),
            calibration_method=calibration_method,
            artifact_path=artifact_path,
            metrics_summary=metrics_summary,
            status="candidate",
            run_id=str(ctx.get("run_id") or run_dir.name),
        )
        candidate_id = candidate_entry.model_id
        candidate_was_registered = True

    if trainer.get("status") in {"blocked", "failed"}:
        if trainer.get("status") == "blocked":
            gate_reasons = ["high_risk_blocked"]
            decision = {"decision": "keep_current", "gate_reasons": gate_reasons, "details": {"blocked_reason": trainer.get("summary")}}
        else:
            gate_reasons = ["training_failed"]
            decision = {"decision": "keep_current", "gate_reasons": gate_reasons, "details": {"error": trainer.get("summary")}}
    else:
        ev = run_step("evaluate", "evaluator", "medium", ctx)
        steps.append(ev)
        d = decide_candidate_upgrade(
            current_metrics=current_metrics,
            candidate_metrics=candidate_metrics,
            pytest_passed=pytest_passed,
            data_quality_ok=data_quality_ok,
            high_confidence_errors_delta=high_conf_delta,
            cross_season_logloss_difference=ctx.get(
                "cross_season_logloss_difference",
                candidate_metrics.get("cross_season_logloss_difference"),
            ),
            bootstrap_ci95_high=ctx.get(
                "bootstrap_ci95_high",
                candidate_metrics.get("bootstrap_ci95_high"),
            ),
            require_cross_season_evidence=bool(ctx.get("require_cross_season_evidence", False)),
        )
        decision = {"decision": d.decision, "gate_reasons": list(d.gate_reasons), "details": d.details}

    if candidate_id and decision:
        if decision.get("decision") == "promote_candidate":
            candidate_entry = mark_production(model_id=candidate_id)
        elif decision.get("decision") == "review_required":
            candidate_entry = set_candidate_status(model_id=candidate_id, status="review_required")
        elif decision.get("decision") == "keep_current":
            candidate_entry = set_candidate_status(model_id=candidate_id, status="rejected")

    production_after = get_current_production_model()
    if candidate_entry is None and candidate_id:
        candidate_entry = find_model(model_id=candidate_id)

    report_path = write_upgrade_report(
        run_dir,
        decision=decision,
        production_model=production_after,
        candidate_model=candidate_entry,
        production_before=production_before,
        allow_high_risk=allow_high_risk,
        candidate_was_registered=candidate_was_registered,
        production_after=production_after,
        standardized_data_path=ctx.get("matches_path"),
        validation_path=validation_path if "validation_path" in locals() else None,
    )
    artifacts, metrics = _aggregate(steps)
    artifacts.append({"name": "upgrade_report", "path": str(report_path), "artifact_type": "json"})
    s = get_settings()
    artifacts.append({"name": "model_registry", "path": str(s.research_model_registry_path), "artifact_type": "json"})
    return {"status": "completed", "steps": steps, "artifacts": artifacts, "metrics": metrics, "decision": decision}
