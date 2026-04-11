from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config.settings import ensure_project_dirs, get_settings


SCHEMA_VERSION = "data_foundation_v1"

REQUIRED_COLUMNS = ["match_id", "odds_home", "odds_draw", "odds_away", "actual_result"]

OPTIONAL_COLUMNS = [
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


def get_schema_columns(*, include_optional: bool = True) -> list[str]:
    cols = list(REQUIRED_COLUMNS)
    if include_optional:
        for c in OPTIONAL_COLUMNS:
            if c not in cols:
                cols.append(c)
    return cols


def write_matches_template_csv(
    *,
    path: str | Path | None = None,
    include_optional: bool = True,
    include_example_row: bool = True,
) -> Path:
    ensure_project_dirs()
    s = get_settings()
    p = Path(path) if path is not None else s.data_matches_template_path
    p.parent.mkdir(parents=True, exist_ok=True)

    cols = get_schema_columns(include_optional=include_optional)
    df = pd.DataFrame(columns=cols)
    if include_example_row:
        example: dict[str, Any] = {c: "" for c in cols}
        example["match_id"] = "example_0001"
        example["odds_home"] = 2.10
        example["odds_draw"] = 3.25
        example["odds_away"] = 3.40
        example["actual_result"] = "H"
        if "date" in cols:
            example["date"] = "2025-01-01"
        if "league" in cols:
            example["league"] = "EPL"
        df = pd.concat([df, pd.DataFrame([example])], ignore_index=True)

    df.to_csv(p, index=False)
    return p


def generate_mock_matches(
    *,
    n: int = 200,
    seed: int = 42,
    start_date: str = "2025-01-01",
    include_optional: bool = True,
) -> pd.DataFrame:
    if n < 3:
        raise ValueError("n 必须 >= 3")
    rng = np.random.default_rng(int(seed))

    dt0 = pd.Timestamp(start_date).date()
    dates = [dt0 + timedelta(days=i) for i in range(n)]
    leagues = np.array(["EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1"])
    league_col = rng.choice(leagues, size=n, replace=True)

    base_strength = rng.normal(loc=0.0, scale=0.8, size=n)
    draw_bias = rng.normal(loc=0.0, scale=0.2, size=n)
    p_home = 1.0 / (1.0 + np.exp(-base_strength))
    p_away = 1.0 - p_home
    p_draw = np.clip(0.22 + 0.08 * np.tanh(draw_bias), 0.12, 0.32)
    scale = (1.0 - p_draw)
    p_home = p_home * scale
    p_away = p_away * scale
    s = p_home + p_draw + p_away
    p_home, p_draw, p_away = p_home / s, p_draw / s, p_away / s

    margin = 1.06
    odds_home = margin / np.clip(p_home, 1e-6, None)
    odds_draw = margin / np.clip(p_draw, 1e-6, None)
    odds_away = margin / np.clip(p_away, 1e-6, None)

    def _snap(odds: np.ndarray, sigma: float) -> np.ndarray:
        x = odds * rng.normal(loc=1.0, scale=sigma, size=odds.shape[0])
        return np.clip(x, 1.01, None)

    odds_home_open = _snap(odds_home, 0.04)
    odds_draw_open = _snap(odds_draw, 0.04)
    odds_away_open = _snap(odds_away, 0.04)

    odds_home_t1 = _snap(odds_home_open, 0.02)
    odds_draw_t1 = _snap(odds_draw_open, 0.02)
    odds_away_t1 = _snap(odds_away_open, 0.02)

    odds_home_t2 = _snap(odds_home_t1, 0.02)
    odds_draw_t2 = _snap(odds_draw_t1, 0.02)
    odds_away_t2 = _snap(odds_away_t1, 0.02)

    odds_home_last = odds_home_t2
    odds_draw_last = odds_draw_t2
    odds_away_last = odds_away_t2

    outcome = np.empty(n, dtype=object)
    for i in range(n):
        outcome[i] = rng.choice(["H", "D", "A"], p=[p_home[i], p_draw[i], p_away[i]])

    xg_home = np.clip(rng.normal(loc=1.35 + 0.25 * base_strength, scale=0.35, size=n), 0.0, None)
    xg_away = np.clip(rng.normal(loc=1.20 - 0.25 * base_strength, scale=0.35, size=n), 0.0, None)

    injury_flag = (rng.random(size=n) < 0.12).astype(int)
    line_move = np.clip(rng.normal(loc=0.0, scale=0.12, size=n), -0.5, 0.5)

    def _hist3(center: np.ndarray, scale: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        v1 = np.clip(rng.normal(loc=center, scale=scale, size=n), 0.0, None)
        v2 = np.clip(rng.normal(loc=center * 0.95, scale=scale, size=n), 0.0, None)
        v3 = np.clip(rng.normal(loc=center * 0.9, scale=scale, size=n), 0.0, None)
        return v1, v2, v3

    home_xg_last_1, home_xg_last_2, home_xg_last_3 = _hist3(xg_home, 0.25)
    away_xg_last_1, away_xg_last_2, away_xg_last_3 = _hist3(xg_away, 0.25)
    home_xga_last_1, home_xga_last_2, home_xga_last_3 = _hist3(xg_away, 0.22)
    away_xga_last_1, away_xga_last_2, away_xga_last_3 = _hist3(xg_home, 0.22)

    df = pd.DataFrame(
        {
            "match_id": [f"mock_{i:05d}" for i in range(n)],
            "odds_home": odds_home.astype(float),
            "odds_draw": odds_draw.astype(float),
            "odds_away": odds_away.astype(float),
            "actual_result": outcome.astype(str),
        }
    )
    if include_optional:
        df["date"] = pd.to_datetime(pd.Series(dates)).astype(str)
        df["league"] = league_col.astype(str)
        df["home_team"] = [f"Home{i%20:02d}" for i in range(n)]
        df["away_team"] = [f"Away{i%20:02d}" for i in range(n)]
        df["xg_home"] = xg_home.astype(float)
        df["xg_away"] = xg_away.astype(float)
        df["injury_flag"] = injury_flag.astype(int)
        df["line_move"] = line_move.astype(float)
        df["odds_home_open"] = odds_home_open.astype(float)
        df["odds_draw_open"] = odds_draw_open.astype(float)
        df["odds_away_open"] = odds_away_open.astype(float)
        df["odds_home_last"] = odds_home_last.astype(float)
        df["odds_draw_last"] = odds_draw_last.astype(float)
        df["odds_away_last"] = odds_away_last.astype(float)
        df["odds_home_t1"] = odds_home_t1.astype(float)
        df["odds_draw_t1"] = odds_draw_t1.astype(float)
        df["odds_away_t1"] = odds_away_t1.astype(float)
        df["odds_home_t2"] = odds_home_t2.astype(float)
        df["odds_draw_t2"] = odds_draw_t2.astype(float)
        df["odds_away_t2"] = odds_away_t2.astype(float)
        df["home_xg_last_1"] = home_xg_last_1.astype(float)
        df["home_xg_last_2"] = home_xg_last_2.astype(float)
        df["home_xg_last_3"] = home_xg_last_3.astype(float)
        df["away_xg_last_1"] = away_xg_last_1.astype(float)
        df["away_xg_last_2"] = away_xg_last_2.astype(float)
        df["away_xg_last_3"] = away_xg_last_3.astype(float)
        df["home_xga_last_1"] = home_xga_last_1.astype(float)
        df["home_xga_last_2"] = home_xga_last_2.astype(float)
        df["home_xga_last_3"] = home_xga_last_3.astype(float)
        df["away_xga_last_1"] = away_xga_last_1.astype(float)
        df["away_xga_last_2"] = away_xga_last_2.astype(float)
        df["away_xga_last_3"] = away_xga_last_3.astype(float)

    return df


def write_mock_matches_csv(
    *,
    path: str | Path | None = None,
    n: int = 200,
    seed: int = 42,
    include_optional: bool = True,
) -> Path:
    ensure_project_dirs()
    s = get_settings()
    p = Path(path) if path is not None else s.data_mock_matches_path
    p.parent.mkdir(parents=True, exist_ok=True)
    df = generate_mock_matches(n=n, seed=seed, include_optional=include_optional)
    df.to_csv(p, index=False)
    return p


@dataclass(frozen=True)
class DataQualityReport:
    schema_version: str
    n_rows: int
    n_unique_match_id: int
    n_duplicate_match_id: int
    date_min: str | None
    date_max: str | None
    league_counts: dict[str, int]
    missing_by_column: dict[str, dict[str, float]]
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "n_rows": int(self.n_rows),
            "n_unique_match_id": int(self.n_unique_match_id),
            "n_duplicate_match_id": int(self.n_duplicate_match_id),
            "date_min": self.date_min,
            "date_max": self.date_max,
            "league_counts": {str(k): int(v) for k, v in self.league_counts.items()},
            "missing_by_column": self.missing_by_column,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def build_missing_report(df: pd.DataFrame) -> pd.DataFrame:
    n = int(len(df))
    rows = []
    for c in df.columns:
        miss = int(df[c].isna().sum())
        rows.append(
            {
                "column": str(c),
                "dtype": str(df[c].dtype),
                "missing_count": miss,
                "missing_rate": float(miss / n) if n else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["missing_rate", "column"], ascending=[False, True], kind="mergesort").reset_index(drop=True)


def validate_matches_df(df: pd.DataFrame) -> DataQualityReport:
    errors: list[str] = []
    warnings: list[str] = []

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        errors.append(f"missing_required_columns={missing_cols}")
        n_rows = int(len(df))
        return DataQualityReport(
            schema_version=SCHEMA_VERSION,
            n_rows=n_rows,
            n_unique_match_id=0,
            n_duplicate_match_id=0,
            date_min=None,
            date_max=None,
            league_counts={},
            missing_by_column={},
            errors=errors,
            warnings=warnings,
        )

    n_rows = int(len(df))
    if n_rows == 0:
        errors.append("empty_dataset")

    match_id = df["match_id"].astype(str)
    n_unique = int(match_id.nunique(dropna=False))
    n_dup = int(match_id.duplicated().sum())
    if n_dup > 0:
        warnings.append(f"duplicate_match_id={n_dup}")

    odds_ok = True
    for col in ("odds_home", "odds_draw", "odds_away"):
        s = pd.to_numeric(df[col], errors="coerce")
        if s.isna().any():
            errors.append(f"odds_not_numeric_or_missing={col}")
            odds_ok = False
        if (s <= 1.0).any():
            warnings.append(f"odds_leq_1_detected={col}")
            odds_ok = False
    if not odds_ok:
        warnings.append("odds_quality_issue")

    actual = df["actual_result"].astype(str).str.upper()
    invalid = sorted(set(actual.unique()) - {"H", "D", "A"})
    if invalid:
        errors.append(f"invalid_actual_result={invalid}")

    date_min = None
    date_max = None
    if "date" in df.columns:
        dt = pd.to_datetime(df["date"], errors="coerce")
        if dt.isna().any():
            warnings.append("date_parse_failed_exists")
        else:
            date_min = str(pd.Timestamp(dt.min()).date())
            date_max = str(pd.Timestamp(dt.max()).date())

    league_counts: dict[str, int] = {}
    if "league" in df.columns:
        vc = df["league"].astype(str).value_counts(dropna=False)
        league_counts = {str(k): int(v) for k, v in vc.items()}

    missing_report = build_missing_report(df)
    missing_by_column = {
        str(r["column"]): {"missing_count": float(r["missing_count"]), "missing_rate": float(r["missing_rate"])}
        for _, r in missing_report.iterrows()
    }

    return DataQualityReport(
        schema_version=SCHEMA_VERSION,
        n_rows=n_rows,
        n_unique_match_id=n_unique,
        n_duplicate_match_id=n_dup,
        date_min=date_min,
        date_max=date_max,
        league_counts=league_counts,
        missing_by_column=missing_by_column,
        errors=errors,
        warnings=warnings,
    )


def assert_valid_matches_df(df: pd.DataFrame) -> None:
    report = validate_matches_df(df)
    if report.errors:
        raise ValueError("; ".join(report.errors))


def write_quality_reports(
    df: pd.DataFrame,
    *,
    report_json_path: str | Path | None = None,
    missing_csv_path: str | Path | None = None,
) -> tuple[Path, Path]:
    ensure_project_dirs()
    s = get_settings()
    report_path = Path(report_json_path) if report_json_path is not None else s.eval_data_quality_report_path
    missing_path = Path(missing_csv_path) if missing_csv_path is not None else s.eval_data_missing_report_path

    report = validate_matches_df(df)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    missing_df = build_missing_report(df)
    missing_path.parent.mkdir(parents=True, exist_ok=True)
    missing_df.to_csv(missing_path, index=False)

    return report_path, missing_path
