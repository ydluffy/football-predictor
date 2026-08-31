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

from data.prematch_intelligence import normalize_prematch_intelligence  # noqa: E402


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate timestamped prematch intelligence")
    parser.add_argument("--input", default="data/manual/prematch_intelligence.csv")
    parser.add_argument("--source-config", default="config/prematch_data_sources.json")
    parser.add_argument("--output", default="data/processed/prematch_intelligence_validated.csv")
    parser.add_argument("--audit-output", default="artifacts/data/prematch_intelligence_validation_latest.json")
    parser.add_argument("--fail-on-rejected", action="store_true")
    args = parser.parse_args()

    source = project_path(args.input)
    frame = pd.read_csv(source, low_memory=False)
    normalized, audit = normalize_prematch_intelligence(
        frame,
        source_config_path=project_path(args.source_config),
    )
    output = project_path(args.output)
    audit_output = project_path(args.audit_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    part = output.with_suffix(output.suffix + ".part")
    normalized.to_csv(part, index=False)
    part.replace(output)
    payload = {
        **audit,
        "input_path": str(source.resolve()),
        "output_path": str(output.resolve()),
        "source_config": str(project_path(args.source_config).resolve()),
        "model_input_allowed": bool(audit["usable_rows"] > 0),
    }
    audit_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.fail_on_rejected and int(audit["rejected_rows"]) > 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
