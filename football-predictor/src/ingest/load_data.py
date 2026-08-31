from __future__ import annotations

from pathlib import Path

import pandas as pd

from config.settings import get_settings
from data.transform_rules import parse_match_dates


REQUIRED_COLUMNS = ["match_id", "odds_home", "odds_draw", "odds_away", "actual_result"]


def load_matches(path: str) -> pd.DataFrame:
    settings = get_settings()
    if path:
        csv_path = Path(path)
        if not csv_path.is_absolute():
            csv_path = (settings.project_root / csv_path).resolve()
    else:
        csv_path = settings.data_raw_dir / "sample_matches.csv"

    df = pd.read_csv(csv_path, low_memory=False)
    if df.empty:
        raise ValueError("空数据：CSV 无任何记录")

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"缺少必需字段: {missing}")

    out = df[REQUIRED_COLUMNS].copy()
    if out.isna().any(axis=None):
        na_cols = [c for c in REQUIRED_COLUMNS if out[c].isna().any()]
        raise ValueError(f"必需字段存在空值: {na_cols}")

    out["match_id"] = out["match_id"].astype(str)
    for col in ("odds_home", "odds_draw", "odds_away"):
        out[col] = pd.to_numeric(out[col], errors="raise").astype(float)
    out["actual_result"] = out["actual_result"].astype(str).str.upper()
    return out


def load_matches_with_meta(path: str, *, extra_columns: list[str] | None = None) -> pd.DataFrame:
    settings = get_settings()
    if path:
        csv_path = Path(path)
        if not csv_path.is_absolute():
            csv_path = (settings.project_root / csv_path).resolve()
    else:
        csv_path = settings.data_raw_dir / "sample_matches.csv"

    df = pd.read_csv(csv_path, low_memory=False)
    if df.empty:
        raise ValueError("空数据：CSV 无任何记录")

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"缺少必需字段: {missing}")

    cols = list(REQUIRED_COLUMNS)
    if extra_columns:
        for c in extra_columns:
            if c in df.columns and c not in cols:
                cols.append(c)
    for c in df.columns:
        if c in cols:
            continue
        if c in {
            "home_team",
            "away_team",
            "home_goals",
            "away_goals",
            "home_shots",
            "away_shots",
            "home_shots_on_target",
            "away_shots_on_target",
            "home_corners",
            "away_corners",
            "home_yellow_cards",
            "away_yellow_cards",
            "home_red_cards",
            "away_red_cards",
        }:
            cols.append(c)
            continue
        if c.startswith(("odds_home_", "odds_draw_", "odds_away_")):
            cols.append(c)
            continue
        if c.startswith(("home_xg_hist_", "away_xg_hist_")):
            cols.append(c)
            continue
        if c.startswith(
            (
                "home_xg_last_",
                "away_xg_last_",
                "home_xga_last_",
                "away_xga_last_",
            )
        ):
            cols.append(c)
            continue

    out = df[cols].copy()
    if out[REQUIRED_COLUMNS].isna().any(axis=None):
        na_cols = [c for c in REQUIRED_COLUMNS if out[c].isna().any()]
        raise ValueError(f"必需字段存在空值: {na_cols}")

    out["match_id"] = out["match_id"].astype(str)
    for col in ("odds_home", "odds_draw", "odds_away"):
        out[col] = pd.to_numeric(out[col], errors="raise").astype(float)
    out["actual_result"] = out["actual_result"].astype(str).str.upper()

    if "date" in out.columns:
        out["date"] = parse_match_dates(out["date"])

    return out


def load_matches_csv(path: Path | None = None) -> pd.DataFrame:
    settings = get_settings()
    csv_path = Path(path) if path is not None else settings.data_raw_dir / "matches.csv"
    return pd.read_csv(csv_path)
