from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from config.settings import get_settings
from data.transform_rules import parse_match_dates
from evaluate.cv_league_summary import summarize_cv_by_league
from evaluate.metrics import compute_metrics
from features.basic_features import build_basic_features
from models.calibration import fit_calibrator, predict_calibrated_proba
from models.model_factory import predict_model_proba, train_model


def run_time_series_cv(
    df: pd.DataFrame,
    feature_version: str = "v1",
    n_splits: int = 3,
    model_type: str = "logit",
    calibration_method: str = "none",
    *,
    date_col: str = "date",
) -> pd.DataFrame:
    if date_col not in df.columns:
        raise ValueError(f"缺少 date 字段: {date_col}")

    data = df.copy()
    data[date_col] = parse_match_dates(data[date_col])
    if data[date_col].isna().any():
        raise ValueError("date 存在无法解析的值")

    data = data.sort_values(date_col, kind="mergesort").reset_index(drop=True)
    if len(data) < 2:
        raise ValueError("样本不足：无法进行时间序列交叉验证")

    if model_type not in {"logit", "lightgbm"}:
        raise ValueError("model_type 仅支持 logit/lightgbm")
    if calibration_method not in {"none", "sigmoid", "isotonic"}:
        raise ValueError("calibration_method 仅支持 none/sigmoid/isotonic")

    X_all, y_all, _ = build_basic_features(data, feature_version=feature_version)
    n_samples = len(X_all)
    if n_splits < 1 or n_splits >= n_samples:
        raise ValueError("样本不足：n_splits 必须小于样本数且至少为 1")

    unique_dates = pd.Index(data[date_col].drop_duplicates())
    if n_splits >= len(unique_dates):
        raise ValueError("比赛日不足：n_splits 必须小于唯一比赛日数量")

    splitter = TimeSeriesSplit(n_splits=n_splits)
    rows: list[dict[str, object]] = []
    fold_pred_rows: list[pd.DataFrame] = []

    for fold, (train_date_idx, test_date_idx) in enumerate(splitter.split(unique_dates)):
        train_dates = unique_dates[train_date_idx]
        test_dates = unique_dates[test_date_idx]
        train_idx = np.flatnonzero(data[date_col].isin(train_dates).to_numpy())
        test_idx = np.flatnonzero(data[date_col].isin(test_dates).to_numpy())
        train_size = int(len(train_idx))
        test_size = int(len(test_idx))
        X_train = X_all.iloc[train_idx]
        y_train = y_all.iloc[train_idx]
        X_test = X_all.iloc[test_idx]
        y_test = y_all.iloc[test_idx]

        if model_type == "lightgbm":
            model = train_model(model_type, X_train, y_train, n_estimators=60)
        else:
            model = train_model(model_type, X_train, y_train)
        proba_raw = predict_model_proba(model_type, model, X_test)
        if model_type == "logit":
            estimator_for_cal = model._pipeline
        else:
            estimator_for_cal = model

        if calibration_method == "none":
            proba = proba_raw
        else:
            calibrator = fit_calibrator(estimator_for_cal, X_train, y_train, method=calibration_method)
            proba = predict_calibrated_proba(calibrator, X_test)

        m = compute_metrics(y_test, proba[["p_home", "p_draw", "p_away"]])
        market_proba = X_test[["norm_home", "norm_draw", "norm_away"]].copy()
        market_proba.columns = ["p_home", "p_draw", "p_away"]
        market_metrics = compute_metrics(y_test, market_proba)

        train_end_date = data.loc[train_idx, date_col].max()
        test_start_date = data.loc[test_idx, date_col].min()
        if train_end_date >= test_start_date:
            raise ValueError("不允许未来数据进入训练集")

        if "league" in data.columns:
            fold_results = proba.copy()
            fold_results["actual"] = y_test
            fold_results["model_type"] = model_type
            fold_results["feature_version"] = feature_version
            fold_results["calibration_method"] = calibration_method
            fold_results["fold"] = int(fold)
            fold_results["league"] = data.loc[test_idx, "league"].astype(str).to_numpy()
            fold_pred_rows.append(
                fold_results[
                    [
                        "model_type",
                        "feature_version",
                        "calibration_method",
                        "fold",
                        "league",
                        "actual",
                        "p_home",
                        "p_draw",
                        "p_away",
                    ]
                ]
            )

        rows.append(
            {
                "fold": int(fold),
                "train_size": train_size,
                "test_size": test_size,
                "model_type": model_type,
                "feature_version": feature_version,
                "calibration_method": calibration_method,
                "brier": float(m["brier"]),
                "logloss": float(m["logloss"]),
                "market_brier": float(market_metrics["brier"]),
                "market_logloss": float(market_metrics["logloss"]),
                "brier_vs_market": float(m["brier"] - market_metrics["brier"]),
                "logloss_vs_market": float(m["logloss"] - market_metrics["logloss"]),
                "train_end_date": str(pd.Timestamp(train_end_date).date()),
                "test_start_date": str(pd.Timestamp(test_start_date).date()),
            }
        )

    out = pd.DataFrame(rows)
    settings = get_settings()
    settings.artifacts_eval_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(settings.eval_cv_results_path, index=False)
    if fold_pred_rows:
        fold_preds = pd.concat(fold_pred_rows, axis=0, ignore_index=True)
        cv_league = summarize_cv_by_league(fold_preds)
        cv_league.to_csv(settings.eval_cv_league_metrics_path, index=False)
    return out
