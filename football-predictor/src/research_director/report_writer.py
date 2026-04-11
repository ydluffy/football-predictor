from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config.settings import ensure_project_dirs, get_settings


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _load_execution_context(run_dir: Path) -> dict[str, Any]:
    manifest = run_dir / "run_manifest.json"
    if not manifest.exists():
        return {}
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return {}
    ctx = payload.get("execution_context")
    return ctx if isinstance(ctx, dict) else {}


def _risk_summary_from_verifier(verifier_path: Path) -> dict[str, Any]:
    df = pd.read_csv(verifier_path)
    if df.empty:
        return {"manual_review_required_count": 0, "risk_flag_top": [], "risk_any_count": 0}

    mrr = int(df.get("manual_review_required", pd.Series([], dtype=bool)).fillna(False).astype(bool).sum())

    risk_any = 0
    counts: dict[str, int] = {}
    raw = df.get("risk_flags")
    if raw is not None:
        for x in raw.fillna("").astype(str).tolist():
            s = x.strip()
            if not s:
                continue
            try:
                flags = json.loads(s)
            except Exception:
                flags = []
            if not isinstance(flags, list):
                flags = []
            flags = [str(f) for f in flags if str(f)]
            if flags:
                risk_any += 1
            for f in flags:
                counts[f] = int(counts.get(f, 0)) + 1

    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    return {
        "manual_review_required_count": mrr,
        "risk_any_count": int(risk_any),
        "risk_flag_top": [{"flag": k, "count": int(v)} for k, v in top],
    }


def _md_kv(lines: list[str], key: str, value: object) -> None:
    lines.append(f"- {key}: {value}")


def _jsonable_obj(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _jsonable_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable_obj(x) for x in obj]
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json")
        except Exception:
            pass
    return str(obj)


def write_daily_report(run_dir: Path, *, predictions_path: Path, verifier_path: Path | None) -> Path:
    ensure_project_dirs()
    s = get_settings()
    run_id = str(run_dir.name)
    exec_ctx = _load_execution_context(run_dir)

    match_count = 0
    try:
        pred_df = pd.read_csv(predictions_path)
        match_count = int(len(pred_df))
    except Exception:
        match_count = 0

    risk_summary: dict[str, Any] = {}
    if verifier_path and verifier_path.exists():
        risk_summary = _risk_summary_from_verifier(verifier_path)

    model_artifact_status = None
    model_load_error = None
    fallback_used = None
    fallback_policy = None
    input_data_mode = None
    standardized_data_path = None
    validation_result = None
    validation_path = None

    try:
        manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    except Exception:
        manifest = {}
    if isinstance(manifest, dict) and isinstance(manifest.get("context"), dict):
        input_data_mode = manifest["context"].get("data_mode")

    data_step = run_dir / "steps" / "data" / "step_result.json"
    if data_step.exists():
        try:
            ds = json.loads(data_step.read_text(encoding="utf-8"))
        except Exception:
            ds = {}
        if isinstance(ds, dict) and isinstance(ds.get("metrics"), dict):
            standardized_data_path = ds["metrics"].get("standardized_data_path")
            if ds["metrics"].get("validation_path"):
                validation_path = ds["metrics"].get("validation_path")
            if ds["metrics"].get("required_fields_missing") is not None:
                validation_result = {"required_fields_missing": ds["metrics"].get("required_fields_missing")}

    if validation_path is None:
        for cand in (run_dir / "import_validation.json", run_dir / "dataset_validation.json"):
            if cand.exists():
                validation_path = str(cand)
                break
    if validation_result is None and validation_path:
        try:
            validation_result = json.loads(Path(str(validation_path)).read_text(encoding="utf-8"))
        except Exception:
            validation_result = None
    predict_step = run_dir / "steps" / "predict" / "step_result.json"
    if predict_step.exists():
        try:
            sp = json.loads(predict_step.read_text(encoding="utf-8"))
        except Exception:
            sp = {}
        if isinstance(sp, dict) and isinstance(sp.get("metrics"), dict):
            m = sp["metrics"]
            model_artifact_status = m.get("model_artifact_status")
            model_load_error = m.get("model_load_error")
            fallback_used = m.get("fallback_used")
            fallback_policy = m.get("fallback_policy")

    payload: dict[str, Any] = {
        "report_type": "daily_prediction",
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "match_count": match_count,
        "input_data_mode": input_data_mode,
        "standardized_data_path": standardized_data_path,
        "validation_path": validation_path,
        "validation_result": validation_result,
        "model_type": exec_ctx.get("model_type"),
        "feature_version": exec_ctx.get("feature_version"),
        "use_verifier": bool(exec_ctx.get("use_verifier", verifier_path is not None)),
        "model_artifact_status": model_artifact_status,
        "model_load_error": model_load_error,
        "fallback_used": fallback_used,
        "fallback_policy": fallback_policy,
        "predictions_path": str(predictions_path),
        "verifier_path": str(verifier_path) if verifier_path else None,
        "key_artifacts": {
            "run_dir": str(run_dir),
            "predictions_csv": str(predictions_path),
            "verifier_csv": str(verifier_path) if verifier_path else None,
        },
        "risk_summary": risk_summary,
    }

    run_json = write_json(run_dir / "daily_report.json", payload)

    report_json = write_json(s.research_daily_prediction_report_json_path, payload)
    lines: list[str] = ["# Daily Prediction Report", ""]
    _md_kv(lines, "run_id", run_id)
    _md_kv(lines, "今日比赛数量", match_count)
    _md_kv(lines, "使用模型", payload.get("model_type"))
    _md_kv(lines, "使用特征版本", payload.get("feature_version"))
    _md_kv(lines, "verifier 是否启用", payload.get("use_verifier"))
    _md_kv(lines, "input_data_mode", payload.get("input_data_mode"))
    _md_kv(lines, "standardized_data_path", payload.get("standardized_data_path"))
    _md_kv(lines, "validation_path", payload.get("validation_path"))
    _md_kv(lines, "model_artifact_status", payload.get("model_artifact_status"))
    _md_kv(lines, "fallback_used", payload.get("fallback_used"))
    _md_kv(lines, "fallback_policy", payload.get("fallback_policy"))
    if payload.get("model_load_error"):
        _md_kv(lines, "model_load_error", payload.get("model_load_error"))
    if payload.get("fallback_used") is True:
        lines.append("")
        lines.append("本次预测非正式模型推理结果（使用赔率代理 fallback）。")
    lines.append("")
    lines.append("## 关键产物路径")
    lines.append("")
    _md_kv(lines, "predictions", payload["predictions_path"])
    _md_kv(lines, "verifier_results", payload["verifier_path"])
    lines.append("")
    lines.append("## 风险标记摘要")
    lines.append("")
    if risk_summary:
        _md_kv(lines, "manual_review_required_count", risk_summary.get("manual_review_required_count"))
        _md_kv(lines, "risk_any_count", risk_summary.get("risk_any_count"))
        top = risk_summary.get("risk_flag_top") or []
        if top:
            lines.append("- risk_flag_top:")
            for item in top:
                lines.append(f"  - {item.get('flag')}: {item.get('count')}")
    else:
        lines.append("- (no verifier results)")

    write_text(s.research_daily_prediction_report_md_path, "\n".join(lines) + "\n")
    _ = report_json
    return run_json


def write_post_match_report(run_dir: Path, *, metrics: dict[str, Any], error_analysis_path: Path | None) -> Path:
    ensure_project_dirs()
    s = get_settings()
    run_id = str(run_dir.name)
    exec_ctx = _load_execution_context(run_dir)

    sample_count = 0
    results_path = run_dir / "post_match_results_proxy.csv"
    if results_path.exists():
        try:
            sample_count = int(len(pd.read_csv(results_path)))
        except Exception:
            sample_count = 0

    high_conf = 0
    under_draw = 0
    if error_analysis_path and error_analysis_path.exists():
        try:
            df = pd.read_csv(error_analysis_path)
            if "error_type" in df.columns:
                vc = df["error_type"].astype(str).value_counts()
                high_conf = int(vc.get("high_confidence_error", 0))
                under_draw = int(vc.get("underestimated_draw", 0))
        except Exception:
            high_conf = 0
            under_draw = 0

    optimizer_summary: dict[str, Any] = {}
    opt_path = run_dir / "optimizer_suggestions.json"
    if opt_path.exists():
        try:
            opt = json.loads(opt_path.read_text(encoding="utf-8"))
        except Exception:
            opt = {}
        sugg = opt.get("suggestions") if isinstance(opt, dict) else None
        if isinstance(sugg, list):
            types: dict[str, int] = {}
            for item in sugg:
                if isinstance(item, dict) and item.get("type"):
                    t = str(item["type"])
                    types[t] = int(types.get(t, 0)) + 1
            optimizer_summary = {"suggestion_count": int(len(sugg)), "type_counts": types}

    payload: dict[str, Any] = {
        "report_type": "post_match_learning",
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sample_count": sample_count,
        "brier": float(metrics.get("brier")) if metrics.get("brier") is not None else None,
        "logloss": float(metrics.get("logloss")) if metrics.get("logloss") is not None else None,
        "high_confidence_error_count": high_conf,
        "underestimated_draw_count": under_draw,
        "optimizer_summary": optimizer_summary,
        "model_type": exec_ctx.get("model_type"),
        "feature_version": exec_ctx.get("feature_version"),
        "metrics": metrics,
        "error_analysis_path": str(error_analysis_path) if error_analysis_path else None,
        "key_artifacts": {
            "run_dir": str(run_dir),
            "results_csv": str(results_path) if results_path.exists() else None,
            "error_analysis_csv": str(error_analysis_path) if error_analysis_path else None,
            "optimizer_suggestions_json": str(opt_path) if opt_path.exists() else None,
        },
    }

    run_json = write_json(run_dir / "post_match_report.json", payload)
    report_json = write_json(s.research_post_match_report_json_path, payload)

    lines: list[str] = ["# Post-Match Learning Report", ""]
    _md_kv(lines, "run_id", run_id)
    _md_kv(lines, "样本数", sample_count)
    _md_kv(lines, "brier", payload.get("brier"))
    _md_kv(lines, "logloss", payload.get("logloss"))
    _md_kv(lines, "高置信错判数", high_conf)
    _md_kv(lines, "低估平局数", under_draw)
    lines.append("")
    lines.append("## Optimizer 建议摘要")
    lines.append("")
    if optimizer_summary:
        _md_kv(lines, "suggestion_count", optimizer_summary.get("suggestion_count"))
        tc = optimizer_summary.get("type_counts") or {}
        if tc:
            lines.append("- type_counts:")
            for k in sorted(tc.keys()):
                lines.append(f"  - {k}: {tc[k]}")
    else:
        lines.append("- (no optimizer suggestions)")

    write_text(s.research_post_match_report_md_path, "\n".join(lines) + "\n")
    _ = report_json
    return run_json


def write_upgrade_report(
    run_dir: Path,
    *,
    decision: dict[str, Any],
    production_model: Any | None = None,
    candidate_model: Any | None = None,
    production_before: Any | None = None,
    production_after: Any | None = None,
    allow_high_risk: bool | None = None,
    candidate_was_registered: bool | None = None,
    standardized_data_path: str | None = None,
    validation_path: str | None = None,
) -> Path:
    promoted_candidate_id = None
    if isinstance(decision, dict) and decision.get("decision") == "promote_candidate":
        cand = _jsonable_obj(candidate_model)
        if isinstance(cand, dict):
            promoted_candidate_id = cand.get("model_id")

    gate_reasons = []
    if isinstance(decision, dict):
        gr = decision.get("gate_reasons")
        if isinstance(gr, list):
            gate_reasons = [str(x) for x in gr]

    payload: dict[str, Any] = {
        "report_type": "candidate_model_upgrade",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_id": str(run_dir.name),
        "production_before": _jsonable_obj(production_before),
        "production_after": _jsonable_obj(production_after if production_after is not None else production_model),
        "current_production_model": _jsonable_obj(production_model),
        "new_candidate_model": _jsonable_obj(candidate_model),
        "decision": decision,
        "gate_reasons": gate_reasons,
        "allow_high_risk": bool(allow_high_risk) if allow_high_risk is not None else None,
        "candidate_was_registered": bool(candidate_was_registered) if candidate_was_registered is not None else None,
        "standardized_data_path": standardized_data_path,
        "validation_path": validation_path,
        "promoted_candidate_id": promoted_candidate_id,
    }
    return write_json(run_dir / "upgrade_report.json", payload)
