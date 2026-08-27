from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config.settings import ensure_project_dirs, get_settings
from data.validate_dataset import validate_matches_dataset
from data.transform_rules import standardize_dataset_values


_AUTO_SYNONYMS: dict[str, list[str]] = {
    "match_id": ["match_id", "id", "fixture_id", "game_id"],
    "date": ["date", "match_date", "kickoff", "kickoff_time", "datetime"],
    "league": ["league", "competition", "comp", "division"],
    "home_team": ["home_team", "home", "HomeTeam", "team_home", "home_name"],
    "away_team": ["away_team", "away", "AwayTeam", "team_away", "away_name"],
    "home_goals": ["home_goals", "FTHG", "full_time_home_goals"],
    "away_goals": ["away_goals", "FTAG", "full_time_away_goals"],
    "odds_home": ["odds_home", "home_odds", "b365h", "B365H", "HomeOdds"],
    "odds_draw": ["odds_draw", "draw_odds", "b365d", "B365D", "DrawOdds"],
    "odds_away": ["odds_away", "away_odds", "b365a", "B365A", "AwayOdds"],
    "actual_result": ["actual_result", "result", "ftr", "FTR", "full_time_result"],
    "xg_home": ["xg_home", "home_xg", "hxg", "home_expected_goals"],
    "xg_away": ["xg_away", "away_xg", "axg", "away_expected_goals"],
    "injury_flag": ["injury_flag", "injury", "injuries", "has_injury"],
    "line_move": ["line_move", "linemove", "odds_move", "market_move"],
    "odds_home_open": ["odds_home_open", "home_odds_open", "OpenHomeOdds"],
    "odds_draw_open": ["odds_draw_open", "draw_odds_open", "OpenDrawOdds"],
    "odds_away_open": ["odds_away_open", "away_odds_open", "OpenAwayOdds"],
    "odds_home_last": ["odds_home_last", "home_odds_last", "CloseHomeOdds"],
    "odds_draw_last": ["odds_draw_last", "draw_odds_last", "CloseDrawOdds"],
    "odds_away_last": ["odds_away_last", "away_odds_last", "CloseAwayOdds"],
}

_RESULT_MAP = {
    "H": "H",
    "D": "D",
    "A": "A",
    "HOME": "H",
    "DRAW": "D",
    "AWAY": "A",
    "home": "H",
    "draw": "D",
    "away": "A",
    "1": "H",
    "X": "D",
    "2": "A",
}


@dataclass(frozen=True)
class IngestResult:
    input_path: Path
    output_path: Path
    mapping_record_path: Path
    validation_path: Path
    missing_report_path: Path
    n_rows: int


def _pick_source_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols_lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in df.columns:
            return cand
        key = cand.lower()
        if key in cols_lower:
            return cols_lower[key]
    return None


def _coerce_actual_result(s: pd.Series) -> pd.Series:
    out = s.astype(str).str.strip().str.upper().map(_RESULT_MAP)
    return out


def _apply_transforms(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = standardize_dataset_values(out)
    if "actual_result" in out.columns:
        out["actual_result"] = _coerce_actual_result(out["actual_result"])
    if "match_id" in out.columns:
        out["match_id"] = out["match_id"].astype(str)
    return out


def ingest_matches_csv(
    input_csv_path: str | Path,
    *,
    output_csv_path: str | Path | None = None,
    mapping_spec: dict[str, str | list[str]] | None = None,
    mapping_record_path: str | Path | None = None,
    validation_path: str | Path | None = None,
    missing_report_path: str | Path | None = None,
    feature_version: str = "v3",
) -> IngestResult:
    ensure_project_dirs()
    s = get_settings()

    inp = Path(input_csv_path)
    if not inp.is_absolute():
        inp = (s.project_root / inp).resolve()

    outp = Path(output_csv_path) if output_csv_path is not None else s.data_ingest_output_path
    if not outp.is_absolute():
        outp = (s.project_root / outp).resolve()

    df_in = pd.read_csv(inp)
    if df_in.empty:
        raise ValueError("空数据：CSV 无任何记录")

    mapping_used: dict[str, str | None] = {}
    df_out = pd.DataFrame(index=df_in.index)

    standard_fields = [
        "match_id",
        "date",
        "league",
        "home_team",
        "away_team",
        "home_goals",
        "away_goals",
        "odds_home",
        "odds_draw",
        "odds_away",
        "actual_result",
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
    ]

    for field in standard_fields:
        candidates: list[str] = []
        if mapping_spec and field in mapping_spec:
            spec = mapping_spec[field]
            if isinstance(spec, list):
                candidates = [str(x) for x in spec]
            else:
                candidates = [str(spec)]
        else:
            candidates = _AUTO_SYNONYMS.get(field, [field])

        src = _pick_source_column(df_in, candidates)
        mapping_used[field] = src
        if src is None:
            continue
        df_out[field] = df_in[src]

    df_out = _apply_transforms(df_out)

    match_id_generated = False
    if "match_id" not in df_out.columns:
        match_id_generated = True
        if {"date", "home_team", "away_team"} <= set(df_out.columns):
            base = (
                df_out["date"].astype(str).fillna("")
                + "_"
                + df_out["home_team"].astype(str).fillna("")
                + "_"
                + df_out["away_team"].astype(str).fillna("")
            )
            df_out["match_id"] = base + "_" + pd.Series(range(len(df_out)), index=df_out.index).astype(str)
        else:
            df_out["match_id"] = pd.Series(range(len(df_out)), index=df_out.index).map(lambda i: f"import_{i:06d}")

    required_missing = [c for c in ["odds_home", "odds_draw", "odds_away", "actual_result"] if c not in df_out.columns]
    if required_missing:
        raise ValueError(f"导入后缺少必需字段: {required_missing}")

    outp.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(outp, index=False)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    record = {
        "run_time": now,
        "input_path": str(inp),
        "output_path": str(outp),
        "feature_version": str(feature_version),
        "mapping_used": mapping_used,
        "match_id_generated": bool(match_id_generated),
    }
    mapping_path = Path(mapping_record_path) if mapping_record_path is not None else s.eval_ingest_mapping_record_path
    if not mapping_path.is_absolute():
        mapping_path = (s.project_root / mapping_path).resolve()
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    mapping_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    v_path = Path(validation_path) if validation_path is not None else s.eval_ingest_validation_path
    if not v_path.is_absolute():
        v_path = (s.project_root / v_path).resolve()
    m_path = Path(missing_report_path) if missing_report_path is not None else s.eval_ingest_missing_report_path
    if not m_path.is_absolute():
        m_path = (s.project_root / m_path).resolve()

    payload = validate_matches_dataset(df_out, feature_version, output_json_path=str(v_path), missing_report_csv_path=str(m_path))

    return IngestResult(
        input_path=inp,
        output_path=outp,
        mapping_record_path=mapping_path,
        validation_path=v_path,
        missing_report_path=m_path,
        n_rows=int(len(df_out)),
    )
