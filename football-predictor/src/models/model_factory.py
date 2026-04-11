from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import get_settings
from models.artifact_manifest import (
    ModelArtifactLoadError,
    check_compatibility,
    classify_deserialize_error,
    default_manifest_path_for_artifact,
    read_manifest,
)
from models.baseline_logit import BaselineLogitModel, load_baseline_model
from models.gbdt_lgbm import load_lightgbm_model, predict_lightgbm_proba, save_lightgbm_model, train_lightgbm
from models.stacking_meta import load_stacking_bundle, predict_stacking_proba, save_stacking_bundle, train_stacking_prototype
from models.stacking_oof import (
    load_stacking_oof_bundle,
    predict_stacking_oof_proba,
    save_stacking_oof_bundle,
    train_stacking_oof,
)


SUPPORTED_MODEL_TYPES = {"logit", "lightgbm", "stacking", "stacking_oof"}


def train_model(model_type: str, X, y, **kwargs):
    if model_type not in SUPPORTED_MODEL_TYPES:
        raise ValueError(f"不支持的 model_type: {model_type}")

    if model_type == "logit":
        return BaselineLogitModel().train(X, y)

    if model_type == "stacking":
        random_state = int(kwargs.get("random_state", 42))
        return train_stacking_prototype(X, y, random_state=random_state)

    if model_type == "stacking_oof":
        random_state = int(kwargs.get("random_state", 42))
        if "n_folds" in kwargs:
            n_splits = int(kwargs.get("n_folds"))
        else:
            n_splits = int(kwargs.get("n_splits", 3))
        lightgbm_n_estimators = int(kwargs.get("lightgbm_n_estimators", 80))
        return train_stacking_oof(X, y, n_splits=n_splits, random_state=random_state, lightgbm_n_estimators=lightgbm_n_estimators)

    random_state = int(kwargs.get("random_state", 42))
    n_estimators = int(kwargs.get("n_estimators", 120))
    return train_lightgbm(X, y, random_state=random_state, n_estimators=n_estimators)


def predict_model_proba(model_type: str, model, X) -> pd.DataFrame:
    if model_type not in SUPPORTED_MODEL_TYPES:
        raise ValueError(f"不支持的 model_type: {model_type}")

    if model_type == "logit":
        return model.predict_proba(X)

    if model_type == "stacking":
        proba = predict_stacking_proba(model, X)
        out = pd.DataFrame(proba, columns=["p_home", "p_draw", "p_away"], index=getattr(X, "index", None))
        p = out.to_numpy(dtype=float)
        p = np.clip(p, 1e-15, 1.0)
        row_sum = p.sum(axis=1, keepdims=True)
        row_sum[row_sum == 0.0] = 1.0
        out.loc[:, ["p_home", "p_draw", "p_away"]] = p / row_sum
        return out

    if model_type == "stacking_oof":
        proba = predict_stacking_oof_proba(model, X)
        out = pd.DataFrame(proba, columns=["p_home", "p_draw", "p_away"], index=getattr(X, "index", None))
        p = out.to_numpy(dtype=float)
        p = np.clip(p, 1e-15, 1.0)
        row_sum = p.sum(axis=1, keepdims=True)
        row_sum[row_sum == 0.0] = 1.0
        out.loc[:, ["p_home", "p_draw", "p_away"]] = p / row_sum
        return out

    proba = predict_lightgbm_proba(model, X)
    out = pd.DataFrame(proba, columns=["p_home", "p_draw", "p_away"], index=getattr(X, "index", None))
    p = out.to_numpy(dtype=float)
    p = np.clip(p, 1e-15, 1.0)
    row_sum = p.sum(axis=1, keepdims=True)
    row_sum[row_sum == 0.0] = 1.0
    out.loc[:, ["p_home", "p_draw", "p_away"]] = p / row_sum
    return out


def save_model(model_type: str, model, path: str | Path):
    if model_type not in SUPPORTED_MODEL_TYPES:
        raise ValueError(f"不支持的 model_type: {model_type}")

    if model_type == "logit":
        return model.save(Path(path))

    if model_type == "stacking":
        return save_stacking_bundle(model, path)

    if model_type == "stacking_oof":
        return save_stacking_oof_bundle(model, path)

    return save_lightgbm_model(model, path)


def load_model(model_type: str, path: str | Path):
    if model_type not in SUPPORTED_MODEL_TYPES:
        raise ValueError(f"不支持的 model_type: {model_type}")

    p = Path(path)
    s = get_settings()
    if model_type == "logit" and p == s.logit_model_path:
        mp = s.logit_model_manifest_path
    elif model_type == "lightgbm" and p == s.lightgbm_model_path:
        mp = s.lightgbm_model_manifest_path
    elif model_type == "stacking" and p == s.stacking_meta_model_path:
        mp = s.stacking_meta_model_manifest_path
    elif model_type == "stacking_oof" and p == s.stacking_oof_meta_model_path:
        mp = s.stacking_oof_meta_model_manifest_path
    else:
        mp = default_manifest_path_for_artifact(p)

    manifest = read_manifest(mp)
    if manifest is not None:
        comp = check_compatibility(manifest)
        if not comp.ok:
            raise ModelArtifactLoadError(
                code="env_mismatch",
                message=f"模型环境不兼容: {comp.reason}",
                details={"reason": comp.reason, "details": comp.details, "manifest_path": str(mp), "artifact_path": str(p)},
            )

    if model_type == "logit":
        try:
            return load_baseline_model(p)
        except Exception as e:
            code, details = classify_deserialize_error(e)
            raise ModelArtifactLoadError(code=code, message="模型反序列化失败", details={"artifact_path": str(p), "manifest_path": str(mp), **details}) from e

    if model_type == "stacking":
        try:
            return load_stacking_bundle(p)
        except Exception as e:
            code, details = classify_deserialize_error(e)
            raise ModelArtifactLoadError(code=code, message="模型反序列化失败", details={"artifact_path": str(p), "manifest_path": str(mp), **details}) from e

    if model_type == "stacking_oof":
        try:
            return load_stacking_oof_bundle(p)
        except Exception as e:
            code, details = classify_deserialize_error(e)
            raise ModelArtifactLoadError(code=code, message="模型反序列化失败", details={"artifact_path": str(p), "manifest_path": str(mp), **details}) from e

    try:
        return load_lightgbm_model(p)
    except Exception as e:
        code, details = classify_deserialize_error(e)
        raise ModelArtifactLoadError(code=code, message="模型反序列化失败", details={"artifact_path": str(p), "manifest_path": str(mp), **details}) from e
