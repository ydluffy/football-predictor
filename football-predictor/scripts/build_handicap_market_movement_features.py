from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from features.handicap_market_movement import build_api_football_handicap_movement  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build median multi-bookmaker handicap movement features.")
    parser.add_argument("--history", default="data/external/outer_market_snapshots/history.csv")
    parser.add_argument("--as-of", default="")
    parser.add_argument("--output", default="data/processed/handicap_market_movement_latest.csv")
    parser.add_argument("--audit-output", default="artifacts/data/handicap_market_movement_latest.json")
    args = parser.parse_args()

    history_path = ROOT / args.history
    history = pd.read_csv(history_path, low_memory=False) if history_path.exists() else pd.DataFrame()
    features = build_api_football_handicap_movement(history, as_of=args.as_of or None)
    output = ROOT / args.output
    audit_output = ROOT / args.audit_output
    output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(output, index=False, encoding="utf-8-sig")
    audit = {
        "schema_version": 1,
        "source_rows": int(len(history)),
        "match_rows": int(len(features)),
        "multi_snapshot_matches": int(features["safe_for_shadow_features"].sum()) if not features.empty else 0,
        "median_bookmaker_count": float(features["bookmaker_count"].median()) if not features.empty else 0.0,
        "production_probability_change_allowed": False,
        "stake_increase_allowed": False,
        "output": str(output),
    }
    audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
