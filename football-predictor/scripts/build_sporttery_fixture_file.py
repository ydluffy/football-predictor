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
from world_cup.sporttery_markets import load_sporttery_handicap_markets


def build_sporttery_fixtures(markets: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, row in markets.iterrows():
        date = str(pd.Timestamp(row["date"]).date())
        match_number = str(row.get("match_number", "")).replace(".0", "").zfill(3)
        home = normalize_national_team(row["home_team"])
        away = normalize_national_team(row["away_team"])
        if not home or not away:
            continue
        rows.append(
            {
                "match_id": f"sporttery_{date}_{match_number}",
                "date": date,
                "home_team": home,
                "away_team": away,
                "status": "pre",
                "source": str(row.get("source", "sporttery")),
                "match_number": match_number,
                "kickoff_time": str(row.get("kickoff_time", "")),
            }
        )
    return pd.DataFrame(rows).drop_duplicates(["date", "home_team", "away_team"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a prediction fixture file directly from China Sports Lottery market rows."
    )
    parser.add_argument("--markets", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--audit-output",
        default="artifacts/data/sporttery_fixture_file_import.json",
    )
    args = parser.parse_args()

    markets = load_sporttery_handicap_markets(_ROOT / args.markets)
    fixtures = build_sporttery_fixtures(markets)
    output = _ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    fixtures.to_csv(output, index=False)
    audit = {
        "source": "sporttery_lottery_gov",
        "markets": int(len(markets)),
        "fixtures": int(len(fixtures)),
        "output": str(output),
        "teams": sorted(set(fixtures["home_team"]).union(set(fixtures["away_team"])))
        if not fixtures.empty
        else [],
    }
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
