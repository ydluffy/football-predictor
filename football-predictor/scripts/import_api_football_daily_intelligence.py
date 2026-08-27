from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))

from data.api_football_daily_intelligence import collect_api_football_daily_intelligence
from data.api_football_prematch import append_validated_prematch_intelligence
from world_cup.api_football_adapter import ApiFootballClient


def path(value: str) -> Path:
    item = Path(value); return item if item.is_absolute() else ROOT / item


def load_env() -> None:
    env = ROOT / ".env"
    if not env.exists(): return
    for raw in env.read_text(encoding="utf-8-sig").splitlines():
        if raw.strip() and not raw.lstrip().startswith("#") and "=" in raw:
            key, value = raw.split("=", 1); os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Import mapped daily injuries, lineups and seven-day schedule load.")
    parser.add_argument("--scan-json", required=True); parser.add_argument("--date", required=True)
    parser.add_argument("--stage", choices=["confirm", "final"], required=True)
    parser.add_argument("--observed-at", default=""); parser.add_argument("--request-interval-seconds", type=float, default=6.2)
    parser.add_argument("--raw-root", default="data/external/api_football_daily_intelligence/raw")
    parser.add_argument("--manual-output", default="data/manual/prematch_intelligence.csv")
    parser.add_argument("--validated-output", default="data/processed/prematch_intelligence_validated.csv")
    parser.add_argument("--mapping-output", default="artifacts/data/api_football_daily_mapping_latest.csv")
    parser.add_argument("--audit-output", default="artifacts/data/api_football_daily_intelligence_latest.json")
    args = parser.parse_args(); load_env()
    client = ApiFootballClient(api_key=os.getenv("API_FOOTBALL_KEY", ""))
    if not client.configured: raise SystemExit("API_FOOTBALL_KEY is not configured")
    scan = json.loads(path(args.scan_json).read_text(encoding="utf-8-sig"))
    observed = args.observed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows, mapping, audit = collect_api_football_daily_intelligence(
        client=client, scan_fixtures=pd.DataFrame(scan.get("fixtures") or []), date=args.date,
        observed_at=observed, raw_root=path(args.raw_root), include_lineups=args.stage == "final",
        include_schedule_load=args.stage == "confirm", request_interval_seconds=args.request_interval_seconds,
    )
    mapping_output = path(args.mapping_output); mapping_output.parent.mkdir(parents=True, exist_ok=True)
    mapping.to_csv(mapping_output, index=False, encoding="utf-8-sig")
    audit["write"] = append_validated_prematch_intelligence(
        rows, manual_path=path(args.manual_output), validated_path=path(args.validated_output),
    )
    audit["mapping_output"] = str(mapping_output.resolve())
    audit_output = path(args.audit_output); audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
