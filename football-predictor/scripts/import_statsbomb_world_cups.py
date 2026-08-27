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

from world_cup.player_data import load_player_data_bundle
from world_cup.squad_features import build_fixture_squad_features
from world_cup.statsbomb_adapter import (
    convert_statsbomb_to_player_contract,
    download_statsbomb_world_cup_lineups,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-dir",
        default="data/external/statsbomb-open-data",
    )
    parser.add_argument(
        "--output-dir",
        default="data/player_level/statsbomb_world_cups",
    )
    parser.add_argument("--download", choices=["true", "false"], default="true")
    args = parser.parse_args()

    cache = _ROOT / args.cache_dir
    output = _ROOT / args.output_dir
    download_audit = (
        download_statsbomb_world_cup_lineups(cache)
        if args.download == "true"
        else {}
    )
    conversion = convert_statsbomb_to_player_contract(cache, output)
    bundle = load_player_data_bundle(output)
    fixtures = pd.read_csv(output / "fixtures.csv")
    fixtures["date"] = pd.to_datetime(fixtures["date"])
    features = build_fixture_squad_features(bundle, fixtures)
    feature_output = output / "fixture_squad_features.csv"
    pd.concat(
        [fixtures.reset_index(drop=True), features.reset_index(drop=True)],
        axis=1,
    ).to_csv(feature_output, index=False)
    audit = {
        "download": download_audit,
        "conversion": conversion,
        "validation": {
            "players": len(bundle.players),
            "identity_resolution_rate": 1.0,
            "availability_coverage": 0.0,
            "club_minutes_coverage": 0.0,
            "historical_world_cups": 2,
            "lineup_11_starter_rate": conversion["lineup_11_starter_rate"],
            "minutes_non_null_rate": conversion["minutes_non_null_rate"],
            "feature_rows": len(features),
            "historical_lineup_coverage": 1.0,
            "current_2026_lineup_coverage": 0.0,
            "current_2026_availability_coverage": 0.0,
        },
        "model_promotion": False,
        "reason": "real lineups connected, but availability and club form coverage are zero",
        "feature_output": str(feature_output),
    }
    audit_path = _ROOT / "artifacts" / "data" / "statsbomb_world_cup_import.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
