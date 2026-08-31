from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from strategy.betting_ledger_audit import audit_betting_ledger, render_audit_markdown


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Read-only consistency audit for the betting ledger.")
    parser.add_argument("--ledger", default="data/manual/betting_plan_ledger.csv")
    parser.add_argument("--json-output", default="artifacts/betting/betting_ledger_audit_latest.json")
    parser.add_argument("--markdown-output", default="artifacts/betting/betting_ledger_audit_latest.md")
    parser.add_argument("--fail-on-errors", action="store_true")
    args = parser.parse_args()

    audit = audit_betting_ledger(_ROOT / args.ledger)
    json_path = _ROOT / args.json_output
    markdown_path = _ROOT / args.markdown_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_audit_markdown(audit), encoding="utf-8")
    print(json.dumps(audit["issue_counts"], ensure_ascii=False))
    print(json_path)
    print(markdown_path)
    return 1 if args.fail_on_errors and audit["issue_counts"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
