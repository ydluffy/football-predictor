from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.data_source_audit import audit_prediction_coverage
from world_cup.data_source_audit import audit_source_frame
from world_cup.data_source_audit import registry_as_rows


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit World Cup data acquisition source coverage and prediction-level data gaps."
    )
    parser.add_argument("--as-of-date", default="")
    parser.add_argument(
        "--sporttery-markets",
        default="data/manual/sporttery_handicap_markets_2026-06-26.csv",
    )
    parser.add_argument(
        "--leisu-matches",
        default="data/external/leisu_public_matches.csv",
    )
    parser.add_argument(
        "--espn-fixtures",
        default="data/player_level/espn_world_cup_2026/fixtures.csv",
    )
    parser.add_argument(
        "--espn-squads",
        default="data/player_level/espn_world_cup_2026/squads.csv",
    )
    parser.add_argument(
        "--espn-availability",
        default="data/player_level/espn_world_cup_2026/availability.csv",
    )
    parser.add_argument(
        "--predictions",
        default="artifacts/predictions/world_cup_real_data_2026-06-26.csv",
    )
    parser.add_argument(
        "--structured-intelligence",
        default="data/external/leisu_structured_intelligence.csv",
    )
    parser.add_argument(
        "--public-absence-intelligence",
        default="data/external/public_absence_intelligence.csv",
    )
    parser.add_argument(
        "--api-football-fixtures",
        default="data/external/api_football_world_cup/fixtures.csv",
    )
    parser.add_argument(
        "--sportmonks-fixtures",
        default="data/external/sportmonks_world_cup/fixtures.csv",
    )
    parser.add_argument(
        "--football-data-fixtures",
        default="data/external/football_data_org_world_cup/fixtures.csv",
    )
    parser.add_argument(
        "--the-odds-api-odds",
        default="data/external/the_odds_api_world_cup/odds.csv",
    )
    parser.add_argument(
        "--external-player-profiles",
        default="data/external/external_player_profiles.csv",
    )
    parser.add_argument(
        "--output",
        default="artifacts/data/world_cup_data_source_coverage.json",
    )
    args = parser.parse_args()

    sporttery = _read_csv(_ROOT / args.sporttery_markets)
    leisu = _read_csv(_ROOT / args.leisu_matches)
    fixtures = _read_csv(_ROOT / args.espn_fixtures)
    squads = _read_csv(_ROOT / args.espn_squads)
    availability = _read_csv(_ROOT / args.espn_availability)
    predictions = _read_csv(_ROOT / args.predictions)
    structured_intelligence = _read_csv(_ROOT / args.structured_intelligence)
    public_absence_intelligence = _read_csv(_ROOT / args.public_absence_intelligence)
    api_football_fixtures = _read_csv(_ROOT / args.api_football_fixtures)
    sportmonks_fixtures = _read_csv(_ROOT / args.sportmonks_fixtures)
    football_data_fixtures = _read_csv(_ROOT / args.football_data_fixtures)
    the_odds_api_odds = _read_csv(_ROOT / args.the_odds_api_odds)
    external_player_profiles = _read_csv(_ROOT / args.external_player_profiles)

    espn_frame = fixtures.copy()
    if not squads.empty:
        espn_frame["squad_rows"] = len(squads)
    if not availability.empty:
        espn_frame["availability_rows"] = len(availability)

    source_audits = [
        audit_source_frame(
            "espn_world_cup_live",
            espn_frame,
            expected_rows=104,
            output_path=_ROOT / args.espn_fixtures,
            extra={
                "squad_rows": int(len(squads)),
                "availability_rows": int(len(availability)),
                "availability_gap": int(len(availability)) == 0,
            },
        ),
        audit_source_frame(
            "sporttery_lottery_gov",
            sporttery,
            output_path=_ROOT / args.sporttery_markets,
        ),
        audit_source_frame(
            "leisu_public",
            leisu,
            output_path=_ROOT / args.leisu_matches,
            extra={
                "world_cup_matches": int(
                    leisu["competition"].astype(str).str.contains("世界杯|ä¸–ç•Œæ¯", na=False).sum()
                )
                if "competition" in leisu.columns
                else 0
            },
        ),
        audit_source_frame(
            "leisu_structured_intelligence",
            structured_intelligence,
            output_path=_ROOT / args.structured_intelligence,
        ),
        audit_source_frame(
            "public_absence_intelligence",
            public_absence_intelligence,
            output_path=_ROOT / args.public_absence_intelligence,
            extra={
                "sources": sorted(public_absence_intelligence["source"].dropna().unique().tolist())
                if "source" in public_absence_intelligence.columns
                else [],
                "high_confidence_rows": int(
                    pd.to_numeric(
                        public_absence_intelligence.get("confidence", pd.Series(dtype=float)),
                        errors="coerce",
                    )
                    .fillna(0)
                    .ge(0.6)
                    .sum()
                ),
            },
        ),
        audit_source_frame(
            "api_football",
            api_football_fixtures,
            output_path=_ROOT / args.api_football_fixtures,
        ),
        audit_source_frame(
            "sportmonks",
            sportmonks_fixtures,
            output_path=_ROOT / args.sportmonks_fixtures,
        ),
        audit_source_frame(
            "football_data_org",
            football_data_fixtures,
            expected_rows=104,
            output_path=_ROOT / args.football_data_fixtures,
        ),
        audit_source_frame(
            "the_odds_api",
            the_odds_api_odds,
            output_path=_ROOT / args.the_odds_api_odds,
            extra={
                "events": int(the_odds_api_odds["event_id"].nunique())
                if "event_id" in the_odds_api_odds.columns
                else 0,
                "bookmakers": int(the_odds_api_odds["bookmaker_key"].nunique())
                if "bookmaker_key" in the_odds_api_odds.columns
                else 0,
                "markets": sorted(the_odds_api_odds["market_key"].dropna().unique().tolist())
                if "market_key" in the_odds_api_odds.columns
                else [],
            },
        ),
        audit_source_frame(
            "external_player_profiles",
            external_player_profiles,
            output_path=_ROOT / args.external_player_profiles,
            extra={
                "sources": sorted(external_player_profiles["source"].dropna().unique().tolist())
                if "source" in external_player_profiles.columns
                else [],
                "players_with_market_value": int(
                    pd.to_numeric(
                        external_player_profiles.get("market_value_eur", pd.Series(dtype=float)),
                        errors="coerce",
                    )
                    .fillna(0)
                    .gt(0)
                    .sum()
                ),
            },
        ),
    ]

    prediction_audit = audit_prediction_coverage(predictions)
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "as_of_date": args.as_of_date,
        "registry": registry_as_rows(),
        "source_audits": source_audits,
        "prediction_coverage": prediction_audit,
        "summary": {
            "sources_ok": sum(1 for item in source_audits if item["status"] == "ok"),
            "sources_total": len(source_audits),
            "prediction_status": prediction_audit["status"],
            "critical_missing_dimensions": prediction_audit["critical_missing_dimensions"],
        },
    }

    output = _ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
