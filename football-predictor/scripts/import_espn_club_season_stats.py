from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.espn_club_stats_adapter import import_espn_club_season_stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--player-data-dir", default="data/player_level/espn_world_cup_2026")
    parser.add_argument("--cache-dir", default="data/external/espn-world-cup")
    parser.add_argument("--download", choices=["true", "false"], default="true")
    parser.add_argument("--limit-clubs", type=int)
    parser.add_argument(
        "--audit-output",
        default="artifacts/data/espn_club_season_stats_import.json",
    )
    args = parser.parse_args()
    audit = import_espn_club_season_stats(
        player_data_dir=_ROOT / args.player_data_dir,
        cache_dir=_ROOT / args.cache_dir,
        download=args.download == "true",
        limit_clubs=args.limit_clubs,
    )
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
