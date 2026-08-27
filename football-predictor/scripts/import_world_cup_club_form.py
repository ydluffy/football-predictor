from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.club_form_importer import import_club_form_csv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--player-data-dir",
        default="data/player_level/espn_world_cup_2026",
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--window-days", type=int, default=90)
    parser.add_argument(
        "--audit-output",
        default="artifacts/data/world_cup_club_form_import.json",
    )
    args = parser.parse_args()

    audit = import_club_form_csv(
        player_data_dir=_ROOT / args.player_data_dir,
        input_path=_ROOT / args.input,
        as_of_date=args.as_of_date,
        window_days=args.window_days,
    )
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
