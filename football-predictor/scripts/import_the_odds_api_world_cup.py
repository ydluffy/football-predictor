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

from world_cup.the_odds_api_adapter import import_the_odds_api_world_cup


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
        description="Import FIFA World Cup odds from The Odds API."
    )
    parser.add_argument("--sport-key", default="soccer_fifa_world_cup")
    parser.add_argument("--regions", default="eu,uk,us,au")
    parser.add_argument("--markets", default="h2h,spreads,totals")
    parser.add_argument("--bookmakers", default="")
    parser.add_argument("--api-key", default="", help="Defaults to THE_ODDS_API_KEY environment variable.")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--output-dir", default="data/external/the_odds_api_world_cup")
    parser.add_argument("--audit-output", default="artifacts/data/the_odds_api_world_cup_import.json")
    args = parser.parse_args()

    audit = import_the_odds_api_world_cup(
        output_dir=_ROOT / args.output_dir,
        api_key=args.api_key or os.getenv("THE_ODDS_API_KEY", ""),
        sport_key=args.sport_key,
        regions=args.regions,
        markets=args.markets,
        bookmakers=args.bookmakers,
        timeout=args.timeout,
    )
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
