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

from world_cup.sportmonks_adapter import import_sportmonks_world_cup_realtime


def local_env_value(key: str) -> str:
    """Read one value from the project-local .env without another dependency."""
    env_path = _ROOT / ".env"
    if not env_path.exists():
        return ""
    prefix = f"{key}="
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import World Cup injuries/sidelined players and realtime lineups from SportMonks."
    )
    parser.add_argument("--season-id", required=True, help="SportMonks season id for the competition.")
    parser.add_argument("--date-from", default="")
    parser.add_argument("--date-to", default="")
    parser.add_argument("--api-token", default="", help="Defaults to SPORTMONKS_API_TOKEN environment variable.")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--output-dir", default="data/external/sportmonks_world_cup")
    parser.add_argument("--audit-output", default="artifacts/data/sportmonks_world_cup_realtime_import.json")
    args = parser.parse_args()

    audit = import_sportmonks_world_cup_realtime(
        output_dir=_ROOT / args.output_dir,
        season_id=args.season_id,
        date_from=args.date_from,
        date_to=args.date_to,
        api_token=(
            args.api_token
            or os.getenv("SPORTMONKS_API_TOKEN", "")
            or local_env_value("SPORTMONKS_API_TOKEN")
        ),
        timeout=args.timeout,
    )
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
