from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

import pandas as pd
from pathlib import Path

from config.settings import ensure_project_dirs, get_settings
from data.transform_rules import parse_match_dates


def _feature_version_fields(feature_version: str) -> tuple[list[str], list[str]]:
    fv = str(feature_version)
    required = ["match_id", "odds_home", "odds_draw", "odds_away", "actual_result"]
    if fv == "v1":
        optional = ["date", "league", "home_team", "away_team"]
    elif fv == "v2":
        optional = ["date", "league", "home_team", "away_team", "xg_home", "xg_away", "injury_flag", "line_move"]
    elif fv in {"v3", "v4", "v5", "v6", "v7", "v8"}:
        optional = [
            "date",
            "league",
            "home_team",
            "away_team",
            "xg_home",
            "xg_away",
            "injury_flag",
            "line_move",
            "odds_home_open",
            "odds_draw_open",
            "odds_away_open",
            "odds_home_last",
            "odds_draw_last",
            "odds_away_last",
            "odds_home_t1",
            "odds_draw_t1",
            "odds_away_t1",
            "odds_home_t2",
            "odds_draw_t2",
            "odds_away_t2",
            "home_xg_last_1",
            "home_xg_last_2",
            "home_xg_last_3",
            "away_xg_last_1",
            "away_xg_last_2",
            "away_xg_last_3",
            "home_xga_last_1",
            "home_xga_last_2",
            "home_xga_last_3",
            "away_xga_last_1",
            "away_xga_last_2",
            "away_xga_last_3",
        ]
        if fv in {"v4", "v5", "v6", "v7", "v8"}:
            optional.extend(["home_goals", "away_goals"])
    else:
        raise ValueError("feature_version 仅支持 v1/v2/v3/v4/v5/v6/v7/v8")
    return required, optional


def _normalize_key_part(value: object) -> object:
    if value is None or pd.isna(value):
        return pd.NA
    s = unicodedata.normalize("NFKD", str(value)).strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^0-9a-z]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s if s else pd.NA


def _generate_match_id_series(df: pd.DataFrame) -> pd.Series | None:
    needed = {"date", "league", "home_team", "away_team"}
    if not needed <= set(df.columns):
        return None

    date_key = parse_match_dates(df["date"]).dt.date.astype("string")
    league_key = df["league"].map(_normalize_key_part).astype("string")
    home_key = df["home_team"].map(_normalize_key_part).astype("string")
    away_key = df["away_team"].map(_normalize_key_part).astype("string")
    out = date_key + "_" + league_key + "_" + home_key + "_" + away_key
    out = out.astype("string")
    if int(out.notna().sum()) == 0:
        return None
    return out


def ensure_match_id(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    if "match_id" in df.columns:
        return df, False
    gen = _generate_match_id_series(df)
    if gen is None:
        return df, False
    out = df.copy()
    out["match_id"] = gen
    return out, True


def build_missing_report(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    n = int(len(df))
    for field in df.columns:
        s = df[field]
        non_null = int(s.notna().sum())
        non_null_ratio = float(non_null / n) if n else 0.0

        non_zero_ratio = 0.0
        num = pd.to_numeric(s, errors="coerce")
        if n and num.notna().any():
            denom = float(num.notna().sum())
            if denom > 0:
                non_zero_ratio = float((num.fillna(0.0) != 0.0).sum() / denom)

        rows.append(
            {
                "field": str(field),
                "exists": True,
                "non_null_ratio": non_null_ratio,
                "non_zero_ratio": non_zero_ratio,
            }
        )

    out = pd.DataFrame(rows)
    return out.sort_values(["field"], kind="mergesort").reset_index(drop=True)


def validate_matches_dataset(
    df: pd.DataFrame,
    feature_version: str,
    *,
    output_json_path: str | None = None,
    missing_report_csv_path: str | None = None,
    match_id_generated_hint: bool | None = None,
) -> dict[str, Any]:
    df_work, match_id_generated_internal = ensure_match_id(df)
    match_id_generated = bool(match_id_generated_internal) or bool(match_id_generated_hint) if match_id_generated_hint is not None else bool(match_id_generated_internal)
    required, optional = _feature_version_fields(feature_version)

    required_fields_missing = [c for c in required if c not in df_work.columns]
    optional_fields_missing = [c for c in optional if c not in df_work.columns]
    required_field_null_counts = {
        c: int(df_work[c].isna().sum())
        for c in required
        if c in df_work.columns and int(df_work[c].isna().sum()) > 0
    }

    row_count = int(len(df_work))
    duplicate_match_id_count = 0
    if "match_id" in df_work.columns:
        s_mid = df_work["match_id"].astype("string")
        duplicate_match_id_count = int(s_mid[s_mid.notna()].duplicated().sum())

    parseable_date_ratio = 0.0
    if row_count and "date" in df_work.columns:
        dt = parse_match_dates(df_work["date"])
        parseable_date_ratio = float(dt.notna().sum() / row_count)

    missing = build_missing_report(df_work)
    for f in required_fields_missing + optional_fields_missing:
        if f in missing["field"].values:
            continue
        missing = pd.concat(
            [
                missing,
                pd.DataFrame(
                    [
                        {
                            "field": str(f),
                            "exists": False,
                            "non_null_ratio": 0.0,
                            "non_zero_ratio": 0.0,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    missing = missing.sort_values(["exists", "field"], ascending=[False, True], kind="mergesort").reset_index(drop=True)

    payload: dict[str, Any] = {
        "feature_version": str(feature_version),
        "row_count": row_count,
        "required_fields_missing": required_fields_missing,
        "required_field_null_counts": required_field_null_counts,
        "optional_fields_missing": optional_fields_missing,
        "duplicate_match_id_count": duplicate_match_id_count,
        "parseable_date_ratio": parseable_date_ratio,
        "match_id_generated": bool(match_id_generated),
        "is_trainable": not required_fields_missing and not required_field_null_counts and row_count > 0,
    }

    ensure_project_dirs()
    s = get_settings()
    s.artifacts_eval_dir.mkdir(parents=True, exist_ok=True)
    json_path = s.eval_dataset_validation_path if output_json_path is None else Path(output_json_path)
    csv_path = s.eval_dataset_missing_report_path if missing_report_csv_path is None else Path(missing_report_csv_path)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    missing.to_csv(csv_path, index=False)
    return payload
