from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from strategy.shadow_evidence import settle_shadow_evidence  # noqa: E402


def _path(value: str) -> Path:
    path = Path(value); return path if path.is_absolute() else ROOT / path


def main() -> None:
    parser = argparse.ArgumentParser(description="Settle frozen v2 shadow predictions and virtual plans")
    parser.add_argument("--results-csv", required=True)
    parser.add_argument("--prediction-ledger", default="data/manual/shadow_prediction_ledger_v2.csv")
    parser.add_argument("--portfolio-ledger", default="data/manual/shadow_portfolio_ledger_v2.csv")
    parser.add_argument("--settled-at", required=True)
    parser.add_argument("--audit-output", default="artifacts/data/shadow_evidence_settlement_latest.json")
    args = parser.parse_args()
    audit = settle_shadow_evidence(
        prediction_ledger_path=_path(args.prediction_ledger), portfolio_ledger_path=_path(args.portfolio_ledger),
        results=pd.read_csv(_path(args.results_csv), low_memory=False), settled_at=args.settled_at,
    )
    output = _path(args.audit_output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
