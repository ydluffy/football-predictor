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

from world_cup.public_absence_intelligence import aggregate_public_absences
from world_cup.public_absence_intelligence import load_public_absence_intelligence
from world_cup.public_absence_intelligence import public_absence_summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize public injury/suspension intelligence and export model-ready absences."
    )
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="Input CSV path. Can be passed multiple times.",
    )
    parser.add_argument("--min-confidence", type=float, default=0.6)
    parser.add_argument(
        "--intelligence-output",
        default="data/external/public_absence_intelligence.csv",
    )
    parser.add_argument(
        "--absences-output",
        default="data/external/world_cup_absences.csv",
    )
    parser.add_argument(
        "--audit-output",
        default="artifacts/data/public_absence_intelligence_import.json",
    )
    args = parser.parse_args()

    input_paths = [_ROOT / item for item in args.input]
    intelligence = load_public_absence_intelligence(input_paths)
    absences = aggregate_public_absences(
        intelligence,
        min_confidence=args.min_confidence,
    )

    intelligence_output = _ROOT / args.intelligence_output
    intelligence_output.parent.mkdir(parents=True, exist_ok=True)
    intelligence.to_csv(intelligence_output, index=False)

    absences_output = _ROOT / args.absences_output
    absences_output.parent.mkdir(parents=True, exist_ok=True)
    absences.to_csv(absences_output, index=False)

    audit = {
        "source": "public_absence_intelligence",
        "status": "ok" if not intelligence.empty else "empty",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "inputs": [str(path) for path in input_paths],
        "min_confidence": args.min_confidence,
        "intelligence_output": str(intelligence_output),
        "absences_output": str(absences_output),
        **public_absence_summary(intelligence, absences),
    }
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
