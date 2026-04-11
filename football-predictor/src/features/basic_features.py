from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


_DEFAULT_EXCLUDE_COLS = {"target", "label", "y", "result", "home_goals", "away_goals"}
_REQUIRED_BASIC_COLUMNS = ["odds_home", "odds_draw", "odds_away", "actual_result"]
_RESULT_VALUES = {"H", "D", "A"}
DEFAULT_FEATURE_VERSION = "v2"
SUPPORTED_FEATURE_VERSIONS = {"v1", "v2", "v3"}


def _is_numeric(series: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(series.dtype)


def _pairwise_home_away_diffs(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    home_cols = [c for c in out.columns if c.startswith("home_")]
    away_cols = [c for c in out.columns if c.startswith("away_")]

    home_suffixes = {c[len("home_") :] for c in home_cols}
    away_suffixes = {c[len("away_") :] for c in away_cols}
    common = sorted(home_suffixes & away_suffixes)

    for suffix in common:
        h = f"home_{suffix}"
        a = f"away_{suffix}"
        if _is_numeric(out[h]) and _is_numeric(out[a]):
            out[f"diff_{suffix}"] = out[h] - out[a]

    return out


def build_training_frame(
    df: pd.DataFrame,
    *,
    target_col: str | None = None,
    exclude_cols: Iterable[str] = _DEFAULT_EXCLUDE_COLS,
) -> tuple[pd.DataFrame, pd.Series]:
    data = _pairwise_home_away_diffs(df)

    if target_col and target_col in data.columns:
        y = data[target_col].astype(int)
    elif {"home_goals", "away_goals"} <= set(data.columns):
        y = (data["home_goals"] > data["away_goals"]).astype(int)
    elif "result" in data.columns:
        y = (data["result"].astype(str).str.upper() == "H").astype(int)
    else:
        raise ValueError("无法推断目标列：请提供 target_col 或包含 home_goals/away_goals 或 result(H/A/D)")

    exclude = set(exclude_cols)
    if target_col:
        exclude.add(target_col)

    feature_candidates = [c for c in data.columns if c not in exclude]
    numeric_cols = [c for c in feature_candidates if _is_numeric(data[c])]
    X = data[numeric_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return X, y


def _min_max_normalize(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="raise").astype(float)
    min_v = float(s.min())
    max_v = float(s.max())
    denom = max_v - min_v
    if denom == 0.0:
        return pd.Series(0.0, index=s.index)
    return (s - min_v) / denom


def _safe_numeric_column(df: pd.DataFrame, col: str, *, default: float = 0.0) -> pd.Series:
    if col not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)
    s = pd.to_numeric(df[col], errors="coerce")
    return s.fillna(default).astype(float)


def _coerce_injury_flag(df: pd.DataFrame) -> pd.Series:
    if "injury_flag" not in df.columns:
        return pd.Series(0.0, index=df.index, dtype=float)

    s = df["injury_flag"]
    if pd.api.types.is_bool_dtype(s.dtype):
        return s.astype(int).astype(float)

    if pd.api.types.is_numeric_dtype(s.dtype):
        return pd.to_numeric(s, errors="coerce").fillna(0.0).astype(float)

    mapped = (
        s.astype(str)
        .str.strip()
        .str.lower()
        .map(
            {
                "1": 1.0,
                "true": 1.0,
                "t": 1.0,
                "yes": 1.0,
                "y": 1.0,
                "injured": 1.0,
                "0": 0.0,
                "false": 0.0,
                "f": 0.0,
                "no": 0.0,
                "n": 0.0,
                "": 0.0,
                "none": 0.0,
                "nan": 0.0,
            }
        )
    )
    return mapped.fillna(0.0).astype(float)


def _build_odds_features(df: pd.DataFrame) -> pd.DataFrame:
    odds_home = _safe_numeric_column(df, "odds_home", default=np.nan)
    odds_draw = _safe_numeric_column(df, "odds_draw", default=np.nan)
    odds_away = _safe_numeric_column(df, "odds_away", default=np.nan)

    if odds_home.isna().any() or odds_draw.isna().any() or odds_away.isna().any():
        raise ValueError("odds_* 存在无法解析为数值的缺失/非法值")

    eps = 1e-12
    odds_home = odds_home.clip(lower=eps)
    odds_draw = odds_draw.clip(lower=eps)
    odds_away = odds_away.clip(lower=eps)

    implied_home = 1.0 / odds_home
    implied_draw = 1.0 / odds_draw
    implied_away = 1.0 / odds_away
    implied_sum = (implied_home + implied_draw + implied_away).clip(lower=eps)

    norm_home = implied_home / implied_sum
    norm_draw = implied_draw / implied_sum
    norm_away = implied_away / implied_sum

    odds_diff_home_away = odds_home - odds_away
    draw_vs_avg = norm_draw - (norm_home + norm_away) / 2.0

    X = pd.DataFrame(index=df.index)
    X["implied_home"] = implied_home
    X["implied_draw"] = implied_draw
    X["implied_away"] = implied_away
    X["norm_home"] = norm_home
    X["norm_draw"] = norm_draw
    X["norm_away"] = norm_away
    X["odds_diff_home_away"] = odds_diff_home_away
    X["draw_vs_avg"] = draw_vs_avg
    return X


def build_inference_features(df: pd.DataFrame, *, feature_version: str = DEFAULT_FEATURE_VERSION) -> tuple[pd.DataFrame, list[str]]:
    if df.empty:
        raise ValueError("空数据：DataFrame 无任何记录")

    required = ["odds_home", "odds_draw", "odds_away"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"缺少必需字段: {missing}")

    if feature_version not in SUPPORTED_FEATURE_VERSIONS:
        raise ValueError(f"不支持的 feature_version: {feature_version}")

    X = _build_odds_features(df)
    if feature_version in {"v2", "v3"}:
        xg_home = _safe_numeric_column(df, "xg_home", default=0.0)
        xg_away = _safe_numeric_column(df, "xg_away", default=0.0)
        X["xg_diff"] = xg_home - xg_away
        X["xg_sum"] = xg_home + xg_away
        X["injury_flag"] = _coerce_injury_flag(df)
        X["line_move"] = _safe_numeric_column(df, "line_move", default=0.0)

    if feature_version == "v3":
        from features.kelly_features import build_kelly_proxy_features
        from features.momentum_features import build_momentum_features
        from features.odds_sequence_features import build_odds_sequence_features

        X = pd.concat(
            [
                X,
                build_odds_sequence_features(df),
                build_kelly_proxy_features(df),
                build_momentum_features(df, decay=0.85),
            ],
            axis=1,
        )

    X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    feature_names = list(X.columns)
    return X, feature_names


def build_basic_features(df: pd.DataFrame, *, feature_version: str = DEFAULT_FEATURE_VERSION) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    if df.empty:
        raise ValueError("空数据：DataFrame 无任何记录")

    missing = [c for c in _REQUIRED_BASIC_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"缺少必需字段: {missing}")

    if feature_version not in SUPPORTED_FEATURE_VERSIONS:
        raise ValueError(f"不支持的 feature_version: {feature_version}")

    actual = df["actual_result"].astype(str).str.upper()
    invalid = sorted(set(actual.unique()) - _RESULT_VALUES)
    if invalid:
        raise ValueError(f"actual_result 存在非法取值: {invalid}")

    X = _build_odds_features(df)
    if feature_version in {"v2", "v3"}:
        xg_home = _safe_numeric_column(df, "xg_home", default=0.0)
        xg_away = _safe_numeric_column(df, "xg_away", default=0.0)
        X["xg_diff"] = xg_home - xg_away
        X["xg_sum"] = xg_home + xg_away
        X["injury_flag"] = _coerce_injury_flag(df)
        X["line_move"] = _safe_numeric_column(df, "line_move", default=0.0)

    if feature_version == "v3":
        from features.kelly_features import build_kelly_proxy_features
        from features.momentum_features import build_momentum_features
        from features.odds_sequence_features import build_odds_sequence_features

        X = pd.concat(
            [
                X,
                build_odds_sequence_features(df),
                build_kelly_proxy_features(df),
                build_momentum_features(df, decay=0.85),
            ],
            axis=1,
        )

    X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y = actual
    feature_names = list(X.columns)
    return X, y, feature_names
