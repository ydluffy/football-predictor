from __future__ import annotations

import numpy as np
import pandas as pd

from config.settings import get_settings


def export_lightgbm_feature_importance(model, feature_names: list[str] | None = None) -> pd.DataFrame:
    booster = getattr(model, "booster_", None)
    if booster is None:
        raise ValueError("LightGBM 模型缺少 booster_，无法导出特征重要性")

    names = list(booster.feature_name())
    split_imp = booster.feature_importance(importance_type="split")
    gain_imp = booster.feature_importance(importance_type="gain")

    df = pd.DataFrame({"feature": names, "importance_split": split_imp, "importance_gain": gain_imp})
    df["importance_split"] = pd.to_numeric(df["importance_split"], errors="coerce").fillna(0.0).astype(float)
    df["importance_gain"] = pd.to_numeric(df["importance_gain"], errors="coerce").fillna(0.0).astype(float)
    df = df.sort_values(["importance_gain", "importance_split"], ascending=False).reset_index(drop=True)

    settings = get_settings()
    settings.artifacts_eval_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(settings.eval_lightgbm_feature_importance_path, index=False)
    return df


def try_shap_summary(model, X: pd.DataFrame, *, max_samples: int = 200):
    try:
        import shap
    except Exception as e:
        raise ImportError("shap 不可用：请安装 shap 后再启用 SHAP 分析") from e

    booster = getattr(model, "booster_", None)
    if booster is None:
        raise ValueError("LightGBM 模型缺少 booster_，无法进行 SHAP 分析")

    X_use = X.sample(n=min(len(X), int(max_samples)), random_state=42) if len(X) > max_samples else X
    explainer = shap.TreeExplainer(booster)
    values = explainer.shap_values(X_use)

    if isinstance(values, list):
        arr = np.mean(np.abs(np.stack(values, axis=0)), axis=0)
    else:
        arr = np.abs(values)

    imp = arr.mean(axis=0)
    out = pd.DataFrame({"feature": list(X_use.columns), "mean_abs_shap": imp}).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)
    return out
