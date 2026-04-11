from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from config.settings import get_settings
from evaluate.metrics import compute_metrics, expected_calibration_error, reliability_table
from features.basic_features import build_basic_features


@dataclass(frozen=True)
class EvalOutputs:
    metrics: dict[str, object]
    fold_metrics: pd.DataFrame | None
    reliability: pd.DataFrame


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_dates(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series, errors="coerce")
    if dt.isna().any():
        raise ValueError("date 存在无法解析的值")
    return dt


def _new_logit_pipeline() -> Pipeline:
    return Pipeline(
        steps=[
            ("scaler", StandardScaler(with_mean=False)),
            ("clf", LogisticRegression(max_iter=1000, solver="lbfgs")),
        ]
    )


def _fit_estimator(X: pd.DataFrame, y: pd.Series, *, calibrate: str | None) -> object:
    y_clean = y.astype(str).str.upper()
    base = _new_logit_pipeline()
    if calibrate is None:
        base.fit(X, y_clean)
        return base

    if calibrate not in {"sigmoid", "isotonic"}:
        raise ValueError("calibrate 仅支持 sigmoid/isotonic/None")

    cv = TimeSeriesSplit(n_splits=3)
    clf = CalibratedClassifierCV(estimator=base, method=calibrate, cv=cv)
    clf.fit(X, y_clean)
    return clf


def _classes_of(estimator: object) -> list[str]:
    classes = getattr(estimator, "classes_", None)
    if classes is None and hasattr(estimator, "named_steps"):
        classes = estimator.named_steps["clf"].classes_
    return [str(c).upper() for c in classes]


def _proba_frame(estimator: object, X: pd.DataFrame) -> pd.DataFrame:
    proba = estimator.predict_proba(X)
    classes = _classes_of(estimator)
    mapping = {"H": "p_home", "D": "p_draw", "A": "p_away"}
    out = pd.DataFrame(0.0, index=X.index, columns=["p_home", "p_draw", "p_away"])
    for i, c in enumerate(classes):
        col = mapping.get(c)
        if col:
            out[col] = proba[:, i]
    return out


def time_split_evaluate(
    df: pd.DataFrame,
    *,
    date_col: str = "date",
    test_size: float = 0.2,
    feature_version: str = "v2",
    calibrate: str | None = None,
) -> EvalOutputs:
    if date_col not in df.columns:
        raise ValueError(f"缺少 date 列: {date_col}")

    data = df.copy()
    data[date_col] = _coerce_dates(data[date_col])
    data = data.sort_values(date_col, kind="mergesort").reset_index(drop=True)

    n = len(data)
    split = int(np.floor(n * (1.0 - test_size)))
    if split <= 0 or split >= n:
        raise ValueError("test_size 导致无法切分出训练/测试集")

    train_df = data.iloc[:split].reset_index(drop=True)
    test_df = data.iloc[split:].reset_index(drop=True)

    X_train, y_train, feature_names = build_basic_features(train_df, feature_version=feature_version)
    X_test, y_test, _ = build_basic_features(test_df, feature_version=feature_version)

    est = _fit_estimator(X_train, y_train, calibrate=calibrate)
    proba_test = _proba_frame(est, X_test)

    m = compute_metrics(y_test, proba_test[["p_home", "p_draw", "p_away"]])
    m["ece"] = expected_calibration_error(y_test, proba_test[["p_home", "p_draw", "p_away"]])

    payload: dict[str, object] = {
        "run_time": _utc_now(),
        "eval_type": "time_split",
        "date_col": date_col,
        "split_date": str(test_df[date_col].min().date()),
        "feature_version": feature_version,
        "calibrate": calibrate,
        "n_features": int(len(feature_names)),
        "n_train": int(len(train_df)),
        "n_test": int(len(test_df)),
        **m,
    }

    rel = pd.DataFrame(reliability_table(y_test, proba_test[["p_home", "p_draw", "p_away"]], n_bins=10))
    s = get_settings()
    s.artifacts_eval_dir.mkdir(parents=True, exist_ok=True)
    s.eval_phase3_time_split_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    rel.to_csv(s.eval_phase3_reliability_path, index=False)

    return EvalOutputs(metrics=payload, fold_metrics=None, reliability=rel)


def time_series_cv_evaluate(
    df: pd.DataFrame,
    *,
    date_col: str = "date",
    n_splits: int = 5,
    feature_version: str = "v2",
    calibrate: str | None = None,
) -> EvalOutputs:
    if date_col not in df.columns:
        raise ValueError(f"缺少 date 列: {date_col}")

    data = df.copy()
    data[date_col] = _coerce_dates(data[date_col])
    data = data.sort_values(date_col, kind="mergesort").reset_index(drop=True)

    X_all, y_all, feature_names = build_basic_features(data, feature_version=feature_version)
    splitter = TimeSeriesSplit(n_splits=n_splits)

    fold_rows: list[dict[str, object]] = []
    oof_proba = []
    oof_y = []
    oof_idx = []

    for fold, (train_idx, test_idx) in enumerate(splitter.split(X_all)):
        X_train = X_all.iloc[train_idx]
        y_train = y_all.iloc[train_idx]
        X_val = X_all.iloc[test_idx]
        y_val = y_all.iloc[test_idx]

        est = _fit_estimator(X_train, y_train, calibrate=calibrate)
        proba = _proba_frame(est, X_val)
        m = compute_metrics(y_val, proba[["p_home", "p_draw", "p_away"]])
        ece = expected_calibration_error(y_val, proba[["p_home", "p_draw", "p_away"]])
        fold_rows.append(
            {
                "fold": int(fold),
                "n_train": int(len(train_idx)),
                "n_val": int(len(test_idx)),
                "brier": float(m["brier"]),
                "logloss": float(m["logloss"]),
                "ece": float(ece),
            }
        )
        oof_proba.append(proba)
        oof_y.append(y_val.reset_index(drop=True))
        oof_idx.append(pd.Series(test_idx))

    folds_df = pd.DataFrame(fold_rows)
    proba_all = pd.concat(oof_proba, axis=0).reset_index(drop=True)
    y_concat = pd.concat(oof_y, axis=0).reset_index(drop=True)

    summary = {
        "run_time": _utc_now(),
        "eval_type": "time_series_cv",
        "date_col": date_col,
        "n_splits": int(n_splits),
        "feature_version": feature_version,
        "calibrate": calibrate,
        "n_features": int(len(feature_names)),
        "n_samples": int(len(X_all)),
        "brier_mean": float(folds_df["brier"].mean()),
        "brier_std": float(folds_df["brier"].std(ddof=0)),
        "logloss_mean": float(folds_df["logloss"].mean()),
        "logloss_std": float(folds_df["logloss"].std(ddof=0)),
        "ece_mean": float(folds_df["ece"].mean()),
        "ece_std": float(folds_df["ece"].std(ddof=0)),
        "oof_brier": float(compute_metrics(y_concat, proba_all[["p_home", "p_draw", "p_away"]])["brier"]),
        "oof_logloss": float(compute_metrics(y_concat, proba_all[["p_home", "p_draw", "p_away"]])["logloss"]),
        "oof_ece": float(expected_calibration_error(y_concat, proba_all[["p_home", "p_draw", "p_away"]])),
    }

    rel = pd.DataFrame(reliability_table(y_concat, proba_all[["p_home", "p_draw", "p_away"]], n_bins=10))
    s = get_settings()
    s.artifacts_eval_dir.mkdir(parents=True, exist_ok=True)
    folds_df.to_csv(s.eval_phase3_cv_folds_path, index=False)
    s.eval_phase3_cv_summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    rel.to_csv(s.eval_phase3_reliability_path, index=False)

    return EvalOutputs(metrics=summary, fold_metrics=folds_df, reliability=rel)
