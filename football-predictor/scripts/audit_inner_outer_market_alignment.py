from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data.inner_outer_market_alignment import align_inner_outer_markets, load_sporttery_market_snapshots


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit same-event, time-aligned Sporttery and Asian handicap snapshots.")
    parser.add_argument("--sporttery-index", default="data/manual/sporttery_snapshot_index.csv")
    parser.add_argument("--outer-history", default="data/external/outer_market_snapshots/history.csv")
    parser.add_argument("--max-delta-minutes", type=int, default=30)
    parser.add_argument("--min-aligned-events", type=int, default=300)
    parser.add_argument("--pairs-output", default="artifacts/data/inner_outer_market_alignment_latest.csv")
    parser.add_argument("--audit-output", default="artifacts/data/inner_outer_market_alignment_latest.json")
    args = parser.parse_args()

    sporttery = load_sporttery_market_snapshots(_path(args.sporttery_index))
    outer = pd.read_csv(_path(args.outer_history), low_memory=False)
    pairs, audit = align_inner_outer_markets(sporttery, outer, max_delta_minutes=args.max_delta_minutes)
    audit.update({
        "schema_version": 1, "status": "ok", "min_aligned_events_for_training": args.min_aligned_events,
        "training_ready": audit["time_aligned_events"] >= args.min_aligned_events,
        "interpretation": "identity pairing is not time alignment; only pairs within the configured delta count",
    })
    pairs_output = _path(args.pairs_output); pairs_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output = _path(args.audit_output); audit_output.parent.mkdir(parents=True, exist_ok=True)
    pairs.to_csv(pairs_output, index=False, encoding="utf-8-sig")
    audit["pairs_output"] = str(pairs_output.resolve())
    audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
