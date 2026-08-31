from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from config.settings import get_settings
from ingest.real_data_ingest import ingest_matches_csv


@dataclass(frozen=True)
class PreflightResult:
    status: str
    reasons: list[str]
    details: dict[str, Any]


def _safe_read_csv(path: Path, *, nrows: int = 50) -> pd.DataFrame | None:
    try:
        return pd.read_csv(path, nrows=nrows)
    except Exception:
        return None


def preflight_real_data(
    *,
    raw_matches_csv: str | Path,
    mapping_path: str | Path,
    feature_version: str = "v3",
    min_rows: int = 10,
    min_parseable_date_ratio: float = 0.95,
) -> PreflightResult:
    s = get_settings()
    raw_p = Path(raw_matches_csv)
    if not raw_p.is_absolute():
        raw_p = (s.project_root / raw_p).resolve()
    map_p = Path(mapping_path)
    if not map_p.is_absolute():
        map_p = (s.project_root / map_p).resolve()

    reasons: list[str] = []
    details: dict[str, Any] = {"raw_matches_csv": str(raw_p), "mapping_path": str(map_p)}

    if not raw_p.exists():
        reasons.append("raw_csv_missing")
    if not map_p.exists():
        reasons.append("mapping_missing")
    if reasons:
        return PreflightResult(status="review_required", reasons=reasons, details=details)

    mapping = {}
    try:
        mapping = json.loads(map_p.read_text(encoding="utf-8"))
    except Exception:
        reasons.append("mapping_unreadable")
        return PreflightResult(status="review_required", reasons=reasons, details=details)

    required_standard_fields = mapping.get("required_standard_fields")
    fields = mapping.get("fields")
    if not isinstance(required_standard_fields, list) or not isinstance(fields, dict):
        reasons.append("mapping_schema_invalid")
        return PreflightResult(status="review_required", reasons=reasons, details=details)

    mapped_targets = set(str(v) for v in fields.values())
    missing_map = [str(x) for x in required_standard_fields if str(x) not in mapped_targets]
    if missing_map:
        reasons.append("required_field_mapping_missing")
        details["missing_required_mappings"] = missing_map
        return PreflightResult(status="review_required", reasons=reasons, details=details)

    df_head = _safe_read_csv(raw_p, nrows=5)
    if df_head is None or df_head.empty:
        reasons.append("raw_csv_unreadable")
        return PreflightResult(status="review_required", reasons=reasons, details=details)

    try:
        out = ingest_matches_csv(
            raw_p,
            mapping_spec=mapping,
            feature_version=feature_version,
        )
    except Exception as e:
        reasons.append("ingest_failed")
        details["ingest_error"] = f"{type(e).__name__}: {e}"
        return PreflightResult(status="review_required", reasons=reasons, details=details)

    try:
        df_std = pd.read_csv(out.output_path)
    except Exception:
        reasons.append("standardized_unreadable")
        return PreflightResult(status="review_required", reasons=reasons, details=details)

    row_count = int(len(df_std))
    details["row_count"] = row_count
    if row_count < int(min_rows):
        reasons.append("row_count_too_low")
        details["min_rows"] = int(min_rows)

    parse_ratio = None
    if "date" in df_std.columns:
        dt = pd.to_datetime(df_std["date"], errors="coerce", utc=True, format="mixed")
        parse_ratio = float(dt.notna().mean())
    else:
        parse_ratio = 0.0
    details["parseable_date_ratio"] = parse_ratio
    if parse_ratio < float(min_parseable_date_ratio):
        reasons.append("parseable_date_ratio_too_low")
        details["min_parseable_date_ratio"] = float(min_parseable_date_ratio)

    details["standardized_data_path"] = str(out.output_path)
    details["validation_path"] = str(out.validation_path)
    details["missing_report_path"] = str(out.missing_report_path)

    status = "ok" if not reasons else "review_required"
    return PreflightResult(status=status, reasons=reasons, details=details)
