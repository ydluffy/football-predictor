from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.public_page_text import extract_public_page_text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract visible text from a public football page or cached HTML file."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", default="")
    source.add_argument("--input-html", default="")
    parser.add_argument("--html-output", default="")
    parser.add_argument("--text-output", required=True)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--audit-output", default="artifacts/data/public_page_text_extract.json")
    args = parser.parse_args()

    audit = extract_public_page_text(
        input_path=_ROOT / args.input_html if args.input_html else None,
        url=args.url,
        html_output=_ROOT / args.html_output if args.html_output else None,
        text_output=_ROOT / args.text_output,
        timeout=args.timeout,
    )
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
