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

from models.sporttery_handicap_inference import load_controlled_model, predict_current_handicaps  # noqa: E402


def project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply controlled Sporttery integer-handicap model")
    parser.add_argument("--market-csv", required=True)
    parser.add_argument("--external-history", default="data/manual/external_market_snapshot_history.csv")
    parser.add_argument("--model", default="artifacts/models/sporttery_handicap_margin_v1.joblib")
    parser.add_argument("--metadata", default="artifacts/models/sporttery_handicap_margin_v1.json")
    parser.add_argument("--analysis-at", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()
    model, metadata = load_controlled_model(project_path(args.model), project_path(args.metadata))
    markets = pd.read_csv(project_path(args.market_csv), low_memory=False).fillna("")
    external_path = project_path(args.external_history)
    external = pd.read_csv(external_path, low_memory=False).fillna("") if external_path.exists() else pd.DataFrame()
    predictions, audit = predict_current_handicaps(
        markets, external, model=model, metadata=metadata, analysis_at=args.analysis_at or None
    )
    output = project_path(args.output)
    audit_output = project_path(args.audit_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(output, index=False, encoding="utf-8-sig")
    audit.update({"output": str(output), "market_csv": str(project_path(args.market_csv))})
    audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
