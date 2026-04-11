from __future__ import annotations

import pandas as pd

from config.settings import get_settings


def build_shap_summary(model, X: pd.DataFrame) -> pd.DataFrame:
    try:
        import numpy as np
        import shap
    except Exception as e:
        raise ImportError("shap 不可用：跳过 SHAP 分析") from e

    booster = getattr(model, "booster_", None)
    if booster is None:
        raise ValueError("非 LightGBM 模型：缺少 booster_")

    explainer = shap.TreeExplainer(booster)
    values = explainer.shap_values(X)

    if isinstance(values, list):
        arr = np.mean(np.abs(np.stack(values, axis=0)), axis=0)
    else:
        arr = np.abs(values)

    mean_abs = arr.mean(axis=0)
    out = pd.DataFrame({"feature": list(X.columns), "mean_abs_shap": mean_abs})
    out = out.sort_values(["mean_abs_shap", "feature"], ascending=[False, True]).reset_index(drop=True)
    out["rank"] = (-out["mean_abs_shap"]).rank(method="min").astype(int)

    settings = get_settings()
    settings.artifacts_eval_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(settings.eval_lightgbm_shap_summary_path, index=False)
    return out


def try_build_shap_summary(model, X: pd.DataFrame) -> pd.DataFrame | None:
    try:
        return build_shap_summary(model, X)
    except ImportError:
        return None
