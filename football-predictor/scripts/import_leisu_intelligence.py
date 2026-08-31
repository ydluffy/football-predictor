from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.leisu_intelligence_adapter import import_leisu_intelligence_pages


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch/parse Leisu intelligence pages into structured World Cup intelligence rows."
    )
    parser.add_argument(
        "--leisu-features",
        default="data/external/leisu_world_cup_fixture_features.csv",
    )
    parser.add_argument(
        "--output",
        default="data/external/leisu_structured_intelligence.csv",
    )
    parser.add_argument(
        "--cache-dir",
        default="data/external/leisu-intelligence",
    )
    parser.add_argument("--download", choices=["true", "false"], default="true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--audit-output",
        default="artifacts/data/leisu_structured_intelligence_import.json",
    )
    args = parser.parse_args()

    audit = import_leisu_intelligence_pages(
        leisu_features_path=_ROOT / args.leisu_features,
        output_path=_ROOT / args.output,
        cache_dir=_ROOT / args.cache_dir,
        download=args.download == "true",
        limit=args.limit,
    )
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
