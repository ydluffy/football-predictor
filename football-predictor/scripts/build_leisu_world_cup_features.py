from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.leisu_match_features import export_leisu_fixture_features


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixtures",
        default="data/player_level/espn_world_cup_2026/fixtures.csv",
    )
    parser.add_argument(
        "--leisu-matches",
        default="data/external/leisu_public_matches.csv",
    )
    parser.add_argument(
        "--output",
        default="data/external/leisu_world_cup_fixture_features.csv",
    )
    parser.add_argument(
        "--audit-output",
        default="artifacts/data/leisu_world_cup_fixture_features.json",
    )
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--max-date-delta-days", type=int, default=1)
    args = parser.parse_args()

    audit = export_leisu_fixture_features(
        fixtures_path=_ROOT / args.fixtures,
        leisu_matches_path=_ROOT / args.leisu_matches,
        output_path=_ROOT / args.output,
        audit_output_path=_ROOT / args.audit_output,
        year=args.year,
        max_date_delta_days=args.max_date_delta_days,
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
