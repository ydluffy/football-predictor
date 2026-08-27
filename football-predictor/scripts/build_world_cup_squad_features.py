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

from world_cup.data import normalize_national_team
from world_cup.player_data import load_player_data_bundle
from world_cup.squad_features import build_fixture_squad_features


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--fixtures", required=True)
    parser.add_argument(
        "--output",
        default="data/processed/world_cup_squad_features.csv",
    )
    parser.add_argument(
        "--audit-output",
        default="artifacts/data/world_cup_squad_features.json",
    )
    args = parser.parse_args()

    bundle = load_player_data_bundle(_ROOT / args.data_dir)
    fixtures = pd.read_csv(_ROOT / args.fixtures)
    required = {"date", "home_team", "away_team"}
    missing = required - set(fixtures.columns)
    if missing:
        raise ValueError(f"fixtures missing columns: {sorted(missing)}")
    fixtures["date"] = pd.to_datetime(fixtures["date"], errors="raise")
    known_teams = set(bundle.squads["team"].map(normalize_national_team))
    original_fixture_count = len(fixtures)
    fixtures = fixtures[
        fixtures["home_team"].map(normalize_national_team).isin(known_teams)
        & fixtures["away_team"].map(normalize_national_team).isin(known_teams)
    ].copy()
    features = build_fixture_squad_features(bundle, fixtures)
    output = pd.concat([fixtures.reset_index(drop=True), features.reset_index(drop=True)], axis=1)

    output_path = _ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_path, index=False)

    audit = {
        "fixtures": int(len(fixtures)),
        "skipped_placeholder_fixtures": int(original_fixture_count - len(fixtures)),
        "players": int(len(bundle.players)),
        "aliases": int(len(bundle.aliases)),
        "squad_rows": int(len(bundle.squads)),
        "availability_rows": int(len(bundle.availability)),
        "club_appearance_rows": int(len(bundle.club_appearances)),
        "national_appearance_rows": int(len(bundle.national_appearances)),
        "feature_columns": int(len(features.columns)),
        "output": str(output_path),
    }
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
