from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from quality.data_model_gate import (
    QualityGateConfig,
    QualityGateInputError,
    evaluate_quality_gate,
    load_metrics,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Enforce data freshness, completeness, odds, drift and calibration gates.")
    parser.add_argument("--config", default="config/data_model_quality_gate.json")
    parser.add_argument("--dataset", required=True, help="Current CSV dataset to evaluate.")
    parser.add_argument("--reference", required=True, help="Reference CSV used for PSI drift comparison.")
    parser.add_argument("--metrics", required=True, help="Latest model metrics in JSON or CSV format.")
    parser.add_argument("--output", default="artifacts/eval/data_model_quality_gate.json")
    parser.add_argument("--as-of", help="UTC-aware ISO time; intended for deterministic CI and backfills.")
    return parser


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def main() -> int:
    args = _parser().parse_args()
    output = Path(args.output)
    try:
        config = QualityGateConfig.from_json(args.config)
        current = pd.read_csv(args.dataset)
        reference = pd.read_csv(args.reference)
        as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00")) if args.as_of else None
        report = evaluate_quality_gate(current, reference, load_metrics(args.metrics), config, as_of=as_of)
    except (OSError, pd.errors.ParserError, QualityGateInputError, ValueError) as exc:
        report = {
            "schema_version": 1,
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "status": "error",
            "error": str(exc),
        }
        _write_report(output, report)
        print(f"data_model_quality_gate=error: {exc}", file=sys.stderr)
        print(f"report={output.resolve()}")
        return 2

    _write_report(output, report)
    print(f"data_model_quality_gate={report['status']}")
    print(f"report={output.resolve()}")
    for check in report["checks"]:
        print(f"check.{check['name']}={check['status']}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
