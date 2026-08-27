from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data.the_odds_sporttery import (  # noqa: E402
    capture_sporttery_the_odds_snapshot,
    load_project_env,
)
from data.unified_outer_market_history import build_unified_histories  # noqa: E402


def main() -> None:
    load_project_env()
    parser = argparse.ArgumentParser(
        description="Capture and align an immutable The Odds API snapshot for confirmed Sporttery fixtures."
    )
    parser.add_argument("--scan-json", required=True)
    parser.add_argument("--snapshot-type", choices=["confirm", "final"], required=True)
    parser.add_argument("--sport-keys", default="")
    parser.add_argument("--regions", default="eu,uk,us,au")
    parser.add_argument("--markets", default="h2h,spreads,totals")
    parser.add_argument("--bookmakers", default="")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--kickoff-tolerance-minutes", type=int, default=180)
    parser.add_argument(
        "--snapshot-root", default="data/external/the_odds_api_sporttery/snapshots"
    )
    args = parser.parse_args()

    scan_path = Path(args.scan_json)
    if not scan_path.is_absolute():
        scan_path = ROOT / scan_path
    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    sport_keys = [item.strip() for item in args.sport_keys.split(",") if item.strip()]
    audit = capture_sporttery_the_odds_snapshot(
        scan=scan,
        snapshot_root=ROOT / args.snapshot_root,
        api_key=os.getenv("THE_ODDS_API_KEY", ""),
        snapshot_type=args.snapshot_type,
        regions=args.regions,
        markets=args.markets,
        bookmakers=args.bookmakers,
        timeout=args.timeout,
        kickoff_tolerance_minutes=args.kickoff_tolerance_minutes,
        sport_keys=sport_keys or None,
    )
    outer, model_history, unified_audit = build_unified_histories(
        api_football_history=ROOT / "data" / "external" / "api_football_odds" / "history.csv",
        the_odds_snapshot_root=ROOT / args.snapshot_root,
    )
    outer_path = ROOT / "data" / "external" / "outer_market_snapshots" / "history.csv"
    model_path = ROOT / "data" / "manual" / "external_market_snapshot_history.csv"
    unified_audit_path = ROOT / "artifacts" / "data" / "unified_outer_market_history_latest.json"
    outer_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    outer.to_csv(outer_path, index=False, encoding="utf-8-sig")
    model_history.to_csv(model_path, index=False, encoding="utf-8-sig")
    unified_audit.update({"outer_output": str(outer_path), "model_output": str(model_path)})
    unified_audit_path.write_text(json.dumps(unified_audit, ensure_ascii=False, indent=2), encoding="utf-8")
    audit["unified_history"] = unified_audit
    latest_path = ROOT / "artifacts" / "data" / "the_odds_api_sporttery_latest.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
