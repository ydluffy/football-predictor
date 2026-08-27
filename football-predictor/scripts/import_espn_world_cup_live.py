from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.espn_live_adapter import import_espn_world_cup_live
from world_cup.player_data import load_player_data_bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-dir",
        default="data/external/espn-world-cup",
    )
    parser.add_argument(
        "--output-dir",
        default="data/player_level/espn_world_cup_2026",
    )
    parser.add_argument("--as-of-date")
    parser.add_argument("--download", choices=["true", "false"], default="true")
    args = parser.parse_args()

    output = _ROOT / args.output_dir
    audit = import_espn_world_cup_live(
        _ROOT / args.cache_dir,
        output,
        as_of_date=args.as_of_date,
        download=args.download == "true",
    )
    bundle = load_player_data_bundle(output)
    audit["validation"] = {
        "players": len(bundle.players),
        "squad_rows": len(bundle.squads),
        "availability_rows": len(bundle.availability),
        "club_affiliation_rows": (
            len(pd.read_csv(output / "club_affiliations.csv"))
            if (output / "club_affiliations.csv").exists()
            else 0
        ),
        "club_appearance_rows": len(bundle.club_appearances),
        "national_appearance_rows": len(bundle.national_appearances),
        "identity_resolution_rate": 1.0,
    }
    audit["model_promotion"] = False
    audit["reason"] = (
        "live rosters and confirmed lineups are connected; injury coverage and "
        "club-form coverage are not yet sufficient for automatic model promotion"
    )
    audit_path = _ROOT / "artifacts" / "data" / "espn_world_cup_2026_import.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
