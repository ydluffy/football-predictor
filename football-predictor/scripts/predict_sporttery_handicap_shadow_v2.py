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

from models.sporttery_handicap_shadow_v2_inference import (  # noqa: E402
    load_shadow_model,
    predict_current_handicaps_shadow_v2,
)
from strategy.shadow_evidence import record_shadow_run  # noqa: E402


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run v2 Sporttery handicap inference as a sidecar")
    parser.add_argument("--market-csv", required=True)
    parser.add_argument("--external-history", default="data/manual/external_market_snapshot_history.csv")
    parser.add_argument("--model", default="artifacts/models/sporttery_handicap_shadow_v2.joblib")
    parser.add_argument("--metadata", default="artifacts/models/sporttery_handicap_shadow_v2.json")
    parser.add_argument("--analysis-at", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit-output", required=True)
    parser.add_argument("--stage", choices=["observation", "confirm", "final"], default="observation")
    parser.add_argument("--sales-day", default="")
    parser.add_argument("--prediction-ledger", default="data/manual/shadow_prediction_ledger_v2.csv")
    parser.add_argument("--portfolio-ledger", default="data/manual/shadow_portfolio_ledger_v2.csv")
    parser.add_argument("--config", default="config/shadow_v2.json")
    parser.add_argument("--no-record", action="store_true")
    args = parser.parse_args()

    model, metadata = load_shadow_model(_path(args.model), _path(args.metadata))
    markets = pd.read_csv(_path(args.market_csv), low_memory=False).fillna("")
    external_path = _path(args.external_history)
    external = pd.read_csv(external_path, low_memory=False).fillna("") if external_path.exists() else pd.DataFrame()
    predictions, audit = predict_current_handicaps_shadow_v2(
        markets,
        external,
        model=model,
        metadata=metadata,
        analysis_at=args.analysis_at or None,
    )
    output = _path(args.output)
    audit_output = _path(args.audit_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(output, index=False, encoding="utf-8-sig")
    if not args.no_record:
        sales_day = args.sales_day or str(markets.get("date", pd.Series(dtype=str)).astype(str).min())
        evidence = record_shadow_run(
            predictions, sales_day=sales_day, analysis_at=audit["analysis_at"], stage=args.stage,
            model_id=audit["model_id"], prediction_ledger_path=_path(args.prediction_ledger),
            portfolio_ledger_path=_path(args.portfolio_ledger), config_path=_path(args.config),
        )
        audit["evidence"] = evidence
    audit.update({"output": str(output), "market_csv": str(_path(args.market_csv))})
    audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
