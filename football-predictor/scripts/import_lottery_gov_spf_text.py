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

from world_cup.sporttery_markets import parse_lottery_gov_spf_text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert rendered lottery.gov.cn SPF table text into model-ready Sporttery CSV."
    )
    parser.add_argument("--input", required=True, help="Text copied/exported from the rendered zqspf page.")
    parser.add_argument(
        "--date",
        default="",
        help="Optional match date filter, e.g. 2026-06-26. Without it all parsed matches are written.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Defaults to data/manual/sporttery_handicap_markets_YYYY-MM-DD.csv when --date is set.",
    )
    parser.add_argument("--updated-at", default="", help="Optional captured/updated timestamp.")
    args = parser.parse_args()

    input_path = Path(args.input)
    text = input_path.read_text(encoding="utf-8")
    frame = parse_lottery_gov_spf_text(text, updated_at=args.updated_at)
    if args.date:
        run_date = str(pd.Timestamp(args.date).date())
        frame = frame[frame["date"] == run_date].copy()
    else:
        run_date = ""

    output = (
        _ROOT / args.output
        if args.output
        else (
            _ROOT / "data" / "manual" / f"sporttery_handicap_markets_{run_date}.csv"
            if run_date
            else _ROOT / "data" / "manual" / "lottery_gov_spf_markets.csv"
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False, encoding="utf-8-sig")
    print(
        json.dumps(
            {
                "input": str(input_path),
                "date": args.date or "",
                "rows": int(len(frame)),
                "output": str(output),
                "source": "lottery.gov.cn:zqspf",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
