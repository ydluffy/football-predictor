from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from config.settings import ensure_project_dirs, get_settings
from data.field_mapping import apply_field_mapping, load_field_mapping
from data.import_csv_dataset import import_csv_dataset, summarize_dataset
from data.transform_rules import standardize_dataset_values
from data.validate_dataset import ensure_match_id, validate_matches_dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-path", required=True)
    parser.add_argument("--mapping-path", required=True)
    parser.add_argument("--feature-version", choices=["v1", "v2", "v3"], default="v2")
    args = parser.parse_args()

    ensure_project_dirs()
    s = get_settings()

    df_raw = import_csv_dataset(args.input_path)
    summary = summarize_dataset(df_raw)
    print({"row_count": summary.row_count, "column_count": summary.column_count})

    mapping = load_field_mapping(args.mapping_path)
    df_mapped = apply_field_mapping(df_raw, mapping)
    mapping_summary = dict(df_mapped.attrs.get("mapping_summary") or {})

    df_before = df_mapped.copy()
    df_mapped = standardize_dataset_values(df_mapped)
    if "actual_result" in df_mapped.columns:
        s_res = df_mapped["actual_result"].astype(str).str.strip().str.lower()
        df_mapped["actual_result"] = s_res.map({"home": "H", "draw": "D", "away": "A"}).astype("string")

    df_mapped, match_id_generated = ensure_match_id(df_mapped)

    converted_fields_count = 0
    for c in (
        "date",
        "injury_flag",
        "actual_result",
        "odds_home",
        "odds_draw",
        "odds_away",
        "xg_home",
        "xg_away",
        "line_move",
    ):
        if c in df_before.columns and c in df_mapped.columns:
            if str(df_before[c].dtype) != str(df_mapped[c].dtype):
                converted_fields_count += 1
            else:
                pre_non_null = int(df_before[c].notna().sum())
                post_non_null = int(df_mapped[c].notna().sum())
                if post_non_null != pre_non_null:
                    converted_fields_count += 1

    preview_path = s.data_interim_dir / "imported_preview.csv"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    df_mapped.head(200).to_csv(preview_path, index=False)

    out_path = s.data_processed_dir / "real_matches_standardized.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_mapped.to_csv(out_path, index=False)

    validate_matches_dataset(df_mapped, args.feature_version, match_id_generated_hint=match_id_generated)

    import_summary = {
        "input_path": str(Path(args.input_path)),
        "mapping_path": str(Path(args.mapping_path)),
        "raw_column_count": int(summary.column_count),
        "mapped_column_count": int(df_mapped.shape[1]),
        "missing_required_fields": list(mapping_summary.get("missing_required") or []),
        "converted_fields_count": int(converted_fields_count),
        "unmapped_fields": list(mapping_summary.get("unmapped_source_fields") or []),
        "match_id_generated": bool(match_id_generated),
    }
    if match_id_generated and "match_id" in df_mapped.columns:
        ex = df_mapped["match_id"].astype("string")
        import_summary["match_id_preview"] = [str(x) for x in ex[ex.notna()].head(10).tolist()]
    s.eval_import_summary_path.write_text(json.dumps(import_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    pairs = mapping_summary.get("mapped_pairs") or []
    rows = []
    for p in pairs:
        rows.append(
            {
                "source_field": p.get("source_field"),
                "standard_field": p.get("standard_field"),
                "source_exists": bool(p.get("source_exists")),
                "output_exists": bool(p.get("output_exists")),
            }
        )
    for unmapped in import_summary["unmapped_fields"]:
        rows.append({"source_field": unmapped, "standard_field": None, "source_exists": True, "output_exists": False})
    pd.DataFrame(rows).to_csv(s.eval_field_mapping_report_path, index=False)

    print(str(preview_path))
    print(str(out_path))
    print(str(s.eval_dataset_validation_path))
    print(str(s.eval_dataset_missing_report_path))
    print(str(s.eval_import_summary_path))
    print(str(s.eval_field_mapping_report_path))
    if match_id_generated and "match_id" in df_mapped.columns:
        ex2 = df_mapped["match_id"].astype("string")
        print([str(x) for x in ex2[ex2.notna()].head(10).tolist()])


if __name__ == "__main__":
    main()
