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

from world_cup.api_football_adapter import import_api_football_realtime


def local_env_value(key: str) -> str:
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
        description="Import stable professional football realtime feeds from API-Football/API-SPORTS."
    )
    parser.add_argument("--league-id", type=int, default=1, help="API-Football league id. Default 1 is commonly World Cup.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--date", default="")
    parser.add_argument("--api-key", default="", help="Defaults to API_FOOTBALL_KEY environment variable.")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--output-dir", default="data/external/api_football_world_cup")
    parser.add_argument("--audit-output", default="artifacts/data/api_football_realtime_import.json")
    args = parser.parse_args()

    audit = import_api_football_realtime(
        output_dir=_ROOT / args.output_dir,
        league_id=args.league_id,
        season=args.season,
        date=args.date or None,
        api_key=(
            args.api_key
            or os.getenv("API_FOOTBALL_KEY", "")
            or local_env_value("API_FOOTBALL_KEY")
        ),
        timeout=args.timeout,
    )
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
