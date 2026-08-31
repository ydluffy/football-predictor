from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.public_absence_intelligence import public_absence_summary
from world_cup.public_page_text import read_html_or_text
from world_cup.public_absence_text_parser import parse_public_absence_text_file
from world_cup.public_absence_text_parser import parse_structured_absence_text
from world_cup.public_absence_text_parser import parse_team_news_text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse copied/cached public injury text into normalized absence intelligence CSV."
    )
    source_input = parser.add_mutually_exclusive_group(required=True)
    source_input.add_argument("--input", default="")
    source_input.add_argument("--input-html", default="")
    parser.add_argument("--date", required=True)
    parser.add_argument(
        "--source",
        required=True,
        choices=["transfermarkt", "sports_mole", "fifa", "official_team", "association", "manual"],
    )
    parser.add_argument("--source-url", default="")
    parser.add_argument("--mode", choices=["auto", "structured", "team_news"], default="auto")
    parser.add_argument("--default-team", default="")
    parser.add_argument("--confidence", type=float, default=-1.0)
    parser.add_argument("--output", default="data/external/public_absence_intelligence_parsed.csv")
    parser.add_argument("--audit-output", default="artifacts/data/public_absence_text_parse.json")
    args = parser.parse_args()

    confidence = None if args.confidence < 0 else args.confidence
    if args.input_html:
        _, text = read_html_or_text(_ROOT / args.input_html)
        if args.mode == "structured":
            rows = parse_structured_absence_text(
                text,
                date=args.date,
                source=args.source,
                source_url=args.source_url,
                default_team=args.default_team,
                confidence=confidence,
            )
        elif args.mode == "team_news":
            rows = parse_team_news_text(
                text,
                date=args.date,
                source=args.source,
                source_url=args.source_url,
                confidence=confidence,
            )
        else:
            structured = parse_structured_absence_text(
                text,
                date=args.date,
                source=args.source,
                source_url=args.source_url,
                default_team=args.default_team,
                confidence=confidence,
            )
            team_news = parse_team_news_text(
                text,
                date=args.date,
                source=args.source,
                source_url=args.source_url,
                confidence=confidence,
            )
            if structured.empty:
                rows = team_news
            elif team_news.empty:
                rows = structured
            else:
                import pandas as pd

                from world_cup.public_absence_intelligence import normalize_public_absence_intelligence

                rows = normalize_public_absence_intelligence(pd.concat([structured, team_news], ignore_index=True))
    else:
        rows = parse_public_absence_text_file(
            _ROOT / args.input,
            date=args.date,
            source=args.source,
            source_url=args.source_url,
            mode=args.mode,
            default_team=args.default_team,
            confidence=confidence,
        )
    output = _ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(output, index=False)
    audit = {
        "source": args.source,
        "status": "ok" if not rows.empty else "empty",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "input": str(_ROOT / (args.input or args.input_html)),
        "output": str(output),
        "mode": args.mode,
        **public_absence_summary(rows, rows),
    }
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
