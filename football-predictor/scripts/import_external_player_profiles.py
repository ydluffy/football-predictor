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

from world_cup.external_player_profiles import load_external_player_profiles
from world_cup.external_player_profiles import profile_source_summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize external player profile data such as Transfermarkt market values."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="data/external/external_player_profiles.csv")
    parser.add_argument("--audit-output", default="artifacts/data/external_player_profiles_import.json")
    args = parser.parse_args()

    profiles = load_external_player_profiles(_ROOT / args.input)
    output = _ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    profiles.to_csv(output, index=False)

    audit = {
        "source": "external_player_profiles",
        "status": "ok" if not profiles.empty else "empty",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "input": str(_ROOT / args.input),
        "output": str(output),
        **profile_source_summary(profiles),
    }
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
