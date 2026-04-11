from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_REQUIRED_STANDARD_FIELDS = ["match_id", "odds_home", "odds_draw", "odds_away", "actual_result"]


def load_field_mapping(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    payload = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("mapping 文件必须为 JSON object")
    return payload


def apply_field_mapping(df: pd.DataFrame, mapping: dict[str, Any]) -> pd.DataFrame:
    if not isinstance(mapping, dict):
        raise ValueError("mapping 必须为 dict")

    if "fields" in mapping:
        fields = mapping.get("fields")
        if not isinstance(fields, dict):
            raise ValueError("mapping.fields 必须为 dict")
        keep_unmapped = bool(mapping.get("keep_unmapped", True))
        strict = bool(mapping.get("strict", True))
        required = mapping.get("required_standard_fields", DEFAULT_REQUIRED_STANDARD_FIELDS)
        if not isinstance(required, list) or not all(isinstance(x, str) for x in required):
            raise ValueError("mapping.required_standard_fields 必须为 string list")
    else:
        fields = mapping
        keep_unmapped = True
        strict = True
        required = DEFAULT_REQUIRED_STANDARD_FIELDS

    rename_map: dict[str, str] = {}
    for src, dst in fields.items():
        if not isinstance(src, str) or not isinstance(dst, str):
            raise ValueError("mapping.fields 的 key/value 必须为 string")
        if src in df.columns:
            rename_map[src] = dst

    out = df.rename(columns=rename_map).copy()
    if not keep_unmapped:
        kept = [dst for src, dst in fields.items() if isinstance(dst, str) and dst in out.columns]
        out = out[kept].copy()

    missing_required = [c for c in required if c not in out.columns]
    if missing_required and strict:
        raise ValueError(f"缺少关键字段映射或源字段不存在: {missing_required}")

    mapped_pairs = []
    for src, dst in fields.items():
        mapped_pairs.append(
            {
                "source_field": str(src),
                "standard_field": str(dst),
                "source_exists": bool(src in df.columns),
                "output_exists": bool(str(dst) in out.columns),
            }
        )
    unmapped_source_fields = [str(c) for c in df.columns if str(c) not in set(fields.keys())]

    out.attrs["mapping_summary"] = {
        "mapped_column_count": int(len(rename_map)),
        "keep_unmapped": bool(keep_unmapped),
        "strict": bool(strict),
        "missing_required": missing_required,
        "unmapped_source_fields": unmapped_source_fields,
        "mapped_pairs": mapped_pairs,
    }
    return out
