from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.player_data import load_player_data_bundle
import pandas as pd

from world_cup.external_player_profiles import apply_external_player_profiles
from world_cup.external_player_profiles import load_external_player_profiles
from world_cup.player_strength import apply_club_season_stats, build_player_strengths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir",
        default="data/player_level/espn_world_cup_2026",
    )
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument(
        "--output",
        default="data/player_level/espn_world_cup_2026/player_strengths.csv",
    )
    parser.add_argument(
        "--audit-output",
        default="artifacts/data/world_cup_player_strength.json",
    )
    parser.add_argument(
        "--external-player-profiles",
        default="",
        help="Optional normalized external profiles CSV, e.g. Transfermarkt market values.",
    )
    parser.add_argument("--external-profile-weight", type=float, default=0.12)
    args = parser.parse_args()

    bundle = load_player_data_bundle(_ROOT / args.data_dir)
    strengths = build_player_strengths(bundle, as_of_date=args.as_of_date)
    club_stats_path = _ROOT / args.data_dir / "club_season_stats.csv"
    if club_stats_path.exists():
        club_stats = pd.read_csv(club_stats_path)
        strengths = apply_club_season_stats(strengths, club_stats)
    else:
        club_stats = pd.DataFrame()
    external_profiles = load_external_player_profiles(
        _ROOT / args.external_player_profiles if args.external_player_profiles else None
    )
    if not external_profiles.empty:
        strengths = apply_external_player_profiles(
            strengths,
            external_profiles,
            weight=args.external_profile_weight,
        )
    output = _ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    strengths.to_csv(output, index=False)
    audit = {
        "as_of_date": args.as_of_date,
        "players": int(len(strengths)),
        "players_with_match_evidence": int((strengths["evidence_matches"] > 0).sum()),
        "players_with_recent_club_form": int((strengths["club_matches"] > 0).sum()),
        "recent_club_form_player_coverage": float(
            (strengths["club_matches"] > 0).mean()
        ),
        "players_with_club_season_stats": int(
            (strengths.get("club_season_appearances", pd.Series(0, index=strengths.index)) > 0).sum()
        ),
        "club_season_stats_player_coverage": float(
            (strengths.get("club_season_appearances", pd.Series(0, index=strengths.index)) > 0).mean()
        ),
        "external_player_profiles_loaded": bool(not external_profiles.empty),
        "players_with_external_market_value": int(
            strengths.get("market_value_eur", pd.Series(0, index=strengths.index)).fillna(0).gt(0).sum()
        ),
        "mean_strength_confidence": float(strengths["player_strength_confidence"].mean()),
        "output": str(output),
        "method": "age curve plus national-team and optional 90-day club-form evidence",
    }
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
