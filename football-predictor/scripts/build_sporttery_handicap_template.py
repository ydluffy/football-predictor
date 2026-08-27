from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.sporttery_markets import build_sporttery_template_from_fixtures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument(
        "--fixtures",
        default="data/player_level/espn_world_cup_2026/fixtures.csv",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Defaults to data/manual/sporttery_handicap_markets_YYYY-MM-DD.csv.",
    )
    args = parser.parse_args()

    run_date = str(pd.Timestamp(args.as_of_date).date())
    output = (
        _ROOT / args.output
        if args.output
        else _ROOT / "data" / "manual" / f"sporttery_handicap_markets_{run_date}.csv"
    )
    fixtures = pd.read_csv(_ROOT / args.fixtures)
    template = build_sporttery_template_from_fixtures(
        fixtures,
        as_of_date=run_date,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    template.to_csv(output, index=False, encoding="utf-8-sig")
    print(
        json.dumps(
            {
                "as_of_date": run_date,
                "fixtures": int(len(template)),
                "output": str(output),
                "next_step": "Fill home_handicap from verified China Sports Lottery market.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
