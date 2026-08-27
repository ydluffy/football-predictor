from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data.football_data_org_incremental import COMPETITIONS, import_europe_incremental
from world_cup.football_data_org_adapter import FootballDataOrgClient


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Import immutable football-data.org Europe increments.")
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--competitions", default=",".join(COMPETITIONS))
    parser.add_argument("--output-root", default="data/external/football_data_org_europe")
    parser.add_argument("--audit-output", default="")
    parser.add_argument("--skip-standings", action="store_true")
    parser.add_argument("--include-teams", action="store_true")
    parser.add_argument("--captured-at", default="")
    args = parser.parse_args()

    _load_dotenv(ROOT / ".env")
    token = os.getenv("FOOTBALL_DATA_TOKEN", "").strip()
    if not token:
        raise SystemExit("FOOTBALL_DATA_TOKEN is not configured")
    captured = args.captured_at or datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    codes = [value.strip().upper() for value in args.competitions.split(",") if value.strip()]
    audit = import_europe_incremental(
        client=FootballDataOrgClient(api_token=token), date_from=args.date_from,
        date_to=args.date_to, competitions=codes, captured_at=captured,
        output_root=ROOT / args.output_root, include_standings=not args.skip_standings,
        include_teams=args.include_teams,
    )
    audit_path = Path(args.audit_output) if args.audit_output else ROOT / "artifacts" / "data" / f"football_data_org_europe_{captured[:10]}.json"
    if not audit_path.is_absolute():
        audit_path = ROOT / audit_path
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**audit, "audit_output": str(audit_path.resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
