from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

from config.settings import get_settings


_PROBA_COLS = ["p_home", "p_draw", "p_away"]
_IDX_TO_LABEL = {0: "H", 1: "D", 2: "A"}


def _validate_results_df(df_results: pd.DataFrame) -> pd.DataFrame:
    required = set(_PROBA_COLS) | {"actual"}
    missing = sorted(required - set(df_results.columns))
    if missing:
        raise ValueError(f"缺少字段: {missing}")
    return df_results.copy()


def _attach_risk_columns(df: pd.DataFrame, verifier_results: pd.DataFrame | None) -> pd.DataFrame:
    if {"risk_flags", "manual_review_required"} <= set(df.columns):
        return df

    if verifier_results is None:
        return df
    if "match_id" not in df.columns or "match_id" not in verifier_results.columns:
        return df

    v = verifier_results.copy()
    keep = ["match_id"]
    if "risk_flags" in v.columns:
        keep.append("risk_flags")
    if "manual_review_required" in v.columns:
        keep.append("manual_review_required")
    v = v[keep]
    return df.merge(v, how="left", on="match_id")


def detect_high_confidence_errors(
    df_results: pd.DataFrame,
    prob_threshold: float = 0.8,
    verifier_results: pd.DataFrame | None = None,
) -> pd.DataFrame:
    t = float(prob_threshold)
    if t <= 0.0 or t >= 1.0:
        raise ValueError("prob_threshold 必须在 (0,1) 区间内")

    df = _validate_results_df(df_results)
    df = _attach_risk_columns(df, verifier_results)

    p = df[_PROBA_COLS].to_numpy(dtype=float, copy=False)
    if p.ndim != 2 or p.shape[1] != 3:
        raise ValueError("概率列需要为形状 (n_samples, 3)")
    if not np.isfinite(p).all():
        raise ValueError("概率列存在非有限值")

    max_proba = p.max(axis=1)
    pred_idx = p.argmax(axis=1)
    predicted_label = pd.Series(pred_idx).map(_IDX_TO_LABEL).astype(str).to_numpy()
    actual = df["actual"].astype(str).str.upper().to_numpy()

    mask = (max_proba >= t) & (predicted_label != actual)
    out = df.loc[mask, :].copy()
    out["predicted_label"] = predicted_label[mask]
    out["max_proba"] = max_proba[mask]

    if "match_id" not in out.columns:
        out["match_id"] = None
    if "league" not in out.columns:
        out["league"] = None

    cols = ["match_id", "league", "predicted_label", "actual", "max_proba", "p_home", "p_draw", "p_away"]
    if "risk_flags" in out.columns:
        cols.append("risk_flags")
    if "manual_review_required" in out.columns:
        cols.append("manual_review_required")
    out = out[cols]

    s = get_settings()
    s.artifacts_eval_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(s.eval_high_confidence_errors_path, index=False)
    return out


def detect_underestimated_draws(
    df_results: pd.DataFrame,
    draw_gap_threshold: float = 0.15,
    verifier_results: pd.DataFrame | None = None,
) -> pd.DataFrame:
    t = float(draw_gap_threshold)
    if t <= 0.0 or t >= 1.0:
        raise ValueError("draw_gap_threshold 必须在 (0,1) 区间内")

    df = _validate_results_df(df_results)
    df = _attach_risk_columns(df, verifier_results)
    actual = df["actual"].astype(str).str.upper()
    mask = (actual == "D") & (df["p_draw"].astype(float) < t)

    out = df.loc[mask, :].copy()
    if "match_id" not in out.columns:
        out["match_id"] = None
    if "league" not in out.columns:
        out["league"] = None

    cols = ["match_id", "league", "actual", "p_home", "p_draw", "p_away"]
    if "risk_flags" in out.columns:
        cols.append("risk_flags")
    if "manual_review_required" in out.columns:
        cols.append("manual_review_required")
    out = out[cols]

    s = get_settings()
    s.artifacts_eval_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(s.eval_underestimated_draws_path, index=False)
    return out


def export_error_analysis_with_risk(
    df_results: pd.DataFrame,
    *,
    prob_threshold: float = 0.8,
    draw_gap_threshold: float = 0.15,
    verifier_results: pd.DataFrame | None = None,
    output_csv_path: str | Path | None = None,
) -> pd.DataFrame:
    df = _validate_results_df(df_results)

    if verifier_results is None:
        s = get_settings()
        if s.eval_verifier_results_path.exists():
            verifier_results = pd.read_csv(s.eval_verifier_results_path)

    high = detect_high_confidence_errors(df, prob_threshold=prob_threshold, verifier_results=verifier_results).copy()
    high["error_type"] = "high_confidence_error"
    if "max_proba" in high.columns:
        high["max_proba"] = pd.to_numeric(high["max_proba"], errors="coerce").astype(float)

    draws = detect_underestimated_draws(df, draw_gap_threshold=draw_gap_threshold, verifier_results=verifier_results).copy()
    draws["error_type"] = "underestimated_draw"
    if "predicted_label" not in draws.columns:
        draws["predicted_label"] = None
    if "max_proba" not in draws.columns:
        draws["max_proba"] = np.nan

    out = pd.concat([high, draws], axis=0, ignore_index=True)
    for c in ["risk_flags", "manual_review_required"]:
        if c not in out.columns:
            out[c] = None

    out = out[
        [
            "match_id",
            "league",
            "error_type",
            "predicted_label",
            "actual",
            "max_proba",
            "p_home",
            "p_draw",
            "p_away",
            "risk_flags",
            "manual_review_required",
        ]
    ]

    s = get_settings()
    s.artifacts_eval_dir.mkdir(parents=True, exist_ok=True)
    target = Path(output_csv_path) if output_csv_path is not None else s.eval_error_analysis_with_risk_path
    if not target.is_absolute():
        target = (s.project_root / target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(target, index=False)
    return out
