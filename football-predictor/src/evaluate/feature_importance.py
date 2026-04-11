from __future__ import annotations

import numpy as np
import pandas as pd

from config.settings import get_settings


def build_lightgbm_importance_table(model, feature_names: list[str]) -> pd.DataFrame:
    if not feature_names:
        raise ValueError("feature_names 不能为空")

    booster = getattr(model, "booster_", None)
    if booster is None:
        raise ValueError("非 LightGBM 模型：缺少 booster_")

    names = list(booster.feature_name())
    if names != list(feature_names):
        raise ValueError("feature_names 必须与训练输入特征顺序一致")

    split_imp = booster.feature_importance(importance_type="split")
    gain_imp = booster.feature_importance(importance_type="gain")

    df = pd.DataFrame(
        {
            "feature": names,
            "importance_gain": pd.to_numeric(gain_imp, errors="coerce"),
            "importance_split": pd.to_numeric(split_imp, errors="coerce"),
        }
    )
    df["importance_gain"] = df["importance_gain"].fillna(0.0).astype(float)
    df["importance_split"] = df["importance_split"].fillna(0.0).astype(float)

    df = df.sort_values(["importance_gain", "importance_split", "feature"], ascending=[False, False, True]).reset_index(drop=True)

    df["rank_gain"] = (-df["importance_gain"]).rank(method="min").astype(int)
    df["rank_split"] = (-df["importance_split"]).rank(method="min").astype(int)
    df = df[["feature", "importance_gain", "importance_split", "rank_gain", "rank_split"]]

    settings = get_settings()
    settings.artifacts_eval_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(settings.eval_lightgbm_feature_importance_path, index=False)
    return df
