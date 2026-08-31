from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from data.football_data_org_results import build_sporttery_result_fallback, load_scan_fixtures
from import_sporttery_results import review_ledger, write_review


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a strict football-data.org Sporttery result fallback.")
    parser.add_argument("--scan-json", required=True)
    parser.add_argument("--matches", default="data/external/football_data_org_europe/matches_latest.csv")
    parser.add_argument("--official-markets", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--mapping-output", required=True)
    parser.add_argument("--audit-output", required=True)
    parser.add_argument("--tolerance-minutes", type=int, default=15)
    parser.add_argument("--ledger", default="")
    parser.add_argument("--review-output", default="")
    args = parser.parse_args()

    results, mapping, audit = build_sporttery_result_fallback(
        scan_fixtures=load_scan_fixtures(_path(args.scan_json)),
        football_matches=pd.read_csv(_path(args.matches), low_memory=False),
        official_markets=pd.read_csv(_path(args.official_markets), low_memory=False),
        tolerance_minutes=args.tolerance_minutes,
    )
    output = _path(args.output_csv); output.parent.mkdir(parents=True, exist_ok=True)
    mapping_output = _path(args.mapping_output); mapping_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output = _path(args.audit_output); audit_output.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(output, index=False, encoding="utf-8-sig")
    mapping.to_csv(mapping_output, index=False, encoding="utf-8-sig")
    audit.update({"output_csv": str(output.resolve()), "mapping_output": str(mapping_output.resolve())})
    if args.ledger:
        reviewed = review_ledger(_path(args.ledger), results, output_path=_path(args.ledger))
        audit["ledger_rows"] = int(len(reviewed))
        if args.review_output:
            write_review(_path(args.review_output), reviewed)
            audit["review_output"] = str(_path(args.review_output).resolve())
    audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
