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

from data.external_calendar import build_external_calendar


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="data/external/openfootball")
    parser.add_argument("--matches-path", default="data/processed/historical_matches_trainable.csv")
    parser.add_argument("--output-path", default="data/processed/external_calendar.csv")
    parser.add_argument("--audit-path", default="artifacts/eval/external_calendar_audit.csv")
    args = parser.parse_args()

    matches = pd.read_csv(_ROOT / args.matches_path, usecols=["home_team", "away_team"])
    league_teams = set(matches["home_team"].dropna().astype(str)) | set(
        matches["away_team"].dropna().astype(str)
    )
    calendar, audit = build_external_calendar(
        input_dir=_ROOT / args.input_dir,
        league_teams=league_teams,
    )
    output = _ROOT / args.output_path
    audit_path = _ROOT / args.audit_path
    output.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    calendar.to_csv(output, index=False)
    audit.to_csv(audit_path, index=False)
    summary = {
        "rows": int(len(calendar)),
        "fully_matched_rows": int(
            (calendar["home_team"].notna() & calendar["away_team"].notna()).sum()
        ),
        "target_team_appearances": int(
            calendar["home_team"].notna().sum() + calendar["away_team"].notna().sum()
        ),
        "audit_rows": int(len(audit)),
        "seasons": calendar["season"].value_counts().sort_index().to_dict(),
        "competitions": calendar["competition"].value_counts().sort_index().to_dict(),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
