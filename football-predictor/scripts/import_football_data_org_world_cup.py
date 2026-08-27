from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.football_data_org_adapter import import_football_data_world_cup


def _load_project_env() -> None:
    env_path = _ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    _load_project_env()
    parser = argparse.ArgumentParser(
        description="Import FIFA World Cup fixtures, teams, squads, and coaches from football-data.org."
    )
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--token", default="", help="Defaults to FOOTBALL_DATA_TOKEN environment variable.")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--snapshot-date", default="")
    parser.add_argument("--output-dir", default="data/external/football_data_org_world_cup")
    parser.add_argument("--audit-output", default="artifacts/data/football_data_org_world_cup_import.json")
    args = parser.parse_args()

    audit = import_football_data_world_cup(
        output_dir=_ROOT / args.output_dir,
        season=args.season,
        api_token=args.token
        or os.getenv("FOOTBALL_DATA_TOKEN", "")
        or os.getenv("FOOTBALL_DATA_API_KEY", ""),
        timeout=args.timeout,
        snapshot_date=args.snapshot_date or None,
    )
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
