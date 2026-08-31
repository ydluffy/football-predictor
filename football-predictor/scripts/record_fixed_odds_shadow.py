from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from strategy.fixed_odds_shadow import record_fixed_odds_shadow  # noqa: E402


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Record one final-stage fixed-odds shadow observation")
    parser.add_argument("--plans-csv", required=True)
    parser.add_argument("--sales-day", required=True)
    parser.add_argument("--time-window", required=True)
    parser.add_argument("--analysis-at", required=True)
    parser.add_argument("--stage", choices=["confirm", "final"], required=True)
    parser.add_argument("--virtual-stake", type=float, default=2.0)
    parser.add_argument("--ledger", default="data/manual/fixed_odds_shadow_ledger.csv")
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()

    plans_path = _path(args.plans_csv)
    plans = pd.read_csv(plans_path, keep_default_na=False)
    audit = record_fixed_odds_shadow(
        plans,
        sales_day=args.sales_day,
        time_window=args.time_window,
        analysis_at=args.analysis_at,
        stage=args.stage,
        ledger_path=_path(args.ledger),
        virtual_stake=args.virtual_stake,
        source_plan_csv=str(plans_path),
    )
    audit.update({"plans_csv": str(plans_path), "ledger": str(_path(args.ledger)), "stage": args.stage})
    audit_path = _path(args.audit_output)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
