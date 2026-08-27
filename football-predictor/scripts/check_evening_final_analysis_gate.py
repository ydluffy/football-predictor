from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from strategy.evening_final_gate import CHINA_TZ, evaluate_evening_final_gate, render_gate_markdown


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Hard gate for the pre-cutoff evening final analysis.")
    parser.add_argument("--as-of", default="", help="ISO time in Asia/Shanghai; defaults to now.")
    parser.add_argument("--official-markets", required=True)
    parser.add_argument("--play-odds", required=True)
    parser.add_argument("--matches", required=True, help="Comma-separated Sporttery match numbers.")
    parser.add_argument("--decision-start", default="", help="Optional task-level ISO decision start.")
    parser.add_argument("--decision-lock", default="", help="Optional task-level ISO decision lock.")
    parser.add_argument("--sales-cutoff", default="", help="Optional task-level ISO cutoff; provide all three task deadlines together.")
    parser.add_argument("--output", default="artifacts/betting/evening_final_gate_latest.json")
    parser.add_argument("--markdown-output", default="artifacts/betting/evening_final_gate_latest.md")
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()

    as_of = args.as_of or datetime.now(CHINA_TZ).isoformat()
    gate = evaluate_evening_final_gate(
        as_of=as_of,
        official_markets_path=_ROOT / args.official_markets,
        play_odds_path=_ROOT / args.play_odds,
        expected_match_numbers={value.strip() for value in args.matches.split(",") if value.strip()},
        decision_start=args.decision_start or None,
        decision_lock=args.decision_lock or None,
        sales_cutoff=args.sales_cutoff or None,
    )
    output = _ROOT / args.output
    markdown_output = _ROOT / args.markdown_output
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_output.write_text(render_gate_markdown(gate), encoding="utf-8")
    print(json.dumps({"phase": gate["phase"], "may_create_plan": gate["may_create_plan"]}, ensure_ascii=False))
    print(output)
    print(markdown_output)
    return 2 if args.require_ready and not gate["may_create_plan"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
