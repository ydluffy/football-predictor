from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from config.settings import ensure_project_dirs, get_settings


ALLOWED_MODEL_STATUSES = {"candidate", "production", "archived", "rejected", "review_required"}


class ModelEntry(BaseModel):
    model_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    model_type: str
    feature_version: str
    calibration_method: str
    artifact_path: str
    metrics_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "candidate"
    run_id: str | None = None

    model_config = {"extra": "ignore"}


class ModelRegistry(BaseModel):
    schema_version: str = "model_registry_v2"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    current_production_model: ModelEntry | None = None
    candidate_models: list[ModelEntry] = Field(default_factory=list)

    model_config = {"extra": "ignore"}


def _append_event(*, event_type: str, payload: dict[str, Any]) -> None:
    ensure_project_dirs()
    s = get_settings()
    epath = s.research_registry_events_path
    epath.parent.mkdir(parents=True, exist_ok=True)
    rec = {"event_type": str(event_type), "event_time": datetime.now(timezone.utc).isoformat(), "payload": payload}
    with epath.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_registry() -> ModelRegistry:
    ensure_project_dirs()
    s = get_settings()
    path = s.research_model_registry_path
    if not path.exists():
        return ModelRegistry()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ModelRegistry()

    if isinstance(raw, dict) and raw.get("schema_version") in {"model_registry_v2"}:
        try:
            return ModelRegistry.model_validate(raw)
        except Exception:
            return ModelRegistry()

    try:
        candidates = raw.get("candidates") if isinstance(raw, dict) else None
        legacy = ModelRegistry(current_production_model=None, candidate_models=[])
        if isinstance(candidates, list):
            for c in candidates:
                if not isinstance(c, dict):
                    continue
                legacy.candidate_models.append(
                    ModelEntry(
                        model_id=str(c.get("candidate_id") or uuid.uuid4()),
                        model_type=str(c.get("model_type") or "unknown"),
                        feature_version=str(c.get("feature_version") or "v3"),
                        calibration_method=str(c.get("calibration_method") or "none"),
                        artifact_path=str(c.get("model_path") or ""),
                        metrics_summary={},
                        status=str(c.get("status") or "candidate"),
                        run_id=str(c.get("run_id") or "") if c.get("run_id") else None,
                    )
                )
        return legacy
    except Exception:
        return ModelRegistry()


def save_registry(reg: ModelRegistry) -> None:
    ensure_project_dirs()
    s = get_settings()

    production_count = 0
    if reg.current_production_model is not None and reg.current_production_model.status == "production":
        production_count += 1
    for c in reg.candidate_models:
        if c.status == "production":
            production_count += 1
    if production_count > 1:
        raise ValueError("不允许多个 production 同时存在")

    for c in reg.candidate_models:
        if c.status not in ALLOWED_MODEL_STATUSES:
            raise ValueError(f"非法 status: {c.status}")
    if reg.current_production_model is not None and reg.current_production_model.status not in ALLOWED_MODEL_STATUSES:
        raise ValueError(f"非法 status: {reg.current_production_model.status}")

    reg.updated_at = datetime.now(timezone.utc)
    s.research_model_registry_path.parent.mkdir(parents=True, exist_ok=True)
    s.research_model_registry_path.write_text(reg.model_dump_json(indent=2), encoding="utf-8")


def get_current_production_model() -> ModelEntry | None:
    reg = load_registry()
    if reg.current_production_model is None:
        return None
    if reg.current_production_model.status != "production":
        return None
    return reg.current_production_model


def register_candidate(
    *,
    model_type: str,
    feature_version: str,
    calibration_method: str,
    artifact_path: str,
    metrics_summary: dict[str, Any] | None = None,
    status: str = "candidate",
    run_id: str | None = None,
) -> ModelEntry:
    if status not in ALLOWED_MODEL_STATUSES:
        raise ValueError(f"非法 status: {status}")
    entry = ModelEntry(
        model_type=str(model_type),
        feature_version=str(feature_version),
        calibration_method=str(calibration_method),
        artifact_path=str(artifact_path),
        metrics_summary=dict(metrics_summary or {}),
        status=str(status),
        run_id=run_id,
    )
    reg = load_registry()
    reg.candidate_models.append(entry)
    save_registry(reg)
    _append_event(event_type="register_candidate", payload={"model_id": entry.model_id, "run_id": entry.run_id, "status": entry.status})
    return entry


def mark_production(*, model_id: str) -> ModelEntry:
    reg = load_registry()

    found: ModelEntry | None = None
    remaining: list[ModelEntry] = []
    for c in reg.candidate_models:
        if c.model_id == str(model_id):
            found = c
        else:
            remaining.append(c)

    if found is None and reg.current_production_model is not None and reg.current_production_model.model_id == str(model_id):
        found = reg.current_production_model

    if found is None:
        raise ValueError(f"找不到 model_id: {model_id}")

    if reg.current_production_model is not None and reg.current_production_model.status == "production":
        archived = reg.current_production_model.model_copy(update={"status": "archived"})
        remaining.append(archived)

    promoted = found.model_copy(update={"status": "production"})
    reg.current_production_model = promoted

    for c in remaining:
        if c.status == "production":
            c.status = "archived"
    reg.candidate_models = remaining

    save_registry(reg)
    _append_event(event_type="mark_production", payload={"model_id": promoted.model_id})
    return promoted


def set_candidate_status(*, model_id: str, status: str) -> ModelEntry:
    if status not in ALLOWED_MODEL_STATUSES:
        raise ValueError(f"非法 status: {status}")
    reg = load_registry()
    for i, c in enumerate(reg.candidate_models):
        if c.model_id == str(model_id):
            updated = c.model_copy(update={"status": str(status)})
            reg.candidate_models[i] = updated
            save_registry(reg)
            _append_event(event_type="set_candidate_status", payload={"model_id": updated.model_id, "status": updated.status})
            return updated
    raise ValueError(f"找不到 model_id: {model_id}")


def find_model(*, model_id: str) -> ModelEntry | None:
    reg = load_registry()
    if reg.current_production_model is not None and reg.current_production_model.model_id == str(model_id):
        return reg.current_production_model
    for c in reg.candidate_models:
        if c.model_id == str(model_id):
            return c
    return None


def guess_candidate_artifacts(*, run_dir: Path, model_type: str) -> tuple[str | None, str | None]:
    sandbox_root = run_dir / "sandbox_project"
    models_dir = sandbox_root / "artifacts" / "models"
    eval_dir = sandbox_root / "artifacts" / "eval"

    s = get_settings()
    if not sandbox_root.exists():
        models_dir = s.artifacts_models_dir
        eval_dir = s.artifacts_eval_dir

    if model_type == "lightgbm":
        mp = models_dir / s.lightgbm_model_path.name
    elif model_type == "stacking":
        mp = models_dir / s.stacking_meta_model_path.name
    elif model_type == "stacking_oof":
        mp = models_dir / s.stacking_oof_meta_model_path.name
    else:
        mp = models_dir / s.logit_model_path.name

    metrics_path = eval_dir / s.eval_metrics_path.name
    return (str(mp) if mp.exists() else None, str(metrics_path) if metrics_path.exists() else None)
