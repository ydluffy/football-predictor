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

from world_cup.sporttery_play_odds import parse_lottery_gov_half_full_time_text
from world_cup.sporttery_play_odds import parse_lottery_gov_correct_score_text
from world_cup.sporttery_play_odds import parse_lottery_gov_total_goals_text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--total-goals-text", default="")
    parser.add_argument("--half-full-time-text", default="")
    parser.add_argument("--correct-score-text", default="")
    parser.add_argument("--snapshot-type", default="latest")
    parser.add_argument("--captured-at", default="")
    parser.add_argument(
        "--output",
        default="data/manual/sporttery_play_odds_latest.csv",
    )
    parser.add_argument(
        "--audit-output",
        default="artifacts/data/sporttery_play_odds_import_latest.json",
    )
    args = parser.parse_args()

    frames = []
    if args.total_goals_text:
        text_path = _ROOT / args.total_goals_text
        frames.append(
            parse_lottery_gov_total_goals_text(
                text_path.read_text(encoding="utf-8"),
                snapshot_type=args.snapshot_type,
                captured_at=args.captured_at,
            )
        )
    if args.half_full_time_text:
        text_path = _ROOT / args.half_full_time_text
        frames.append(
            parse_lottery_gov_half_full_time_text(
                text_path.read_text(encoding="utf-8"),
                snapshot_type=args.snapshot_type,
                captured_at=args.captured_at,
            )
        )
    if args.correct_score_text:
        text_path = _ROOT / args.correct_score_text
        frames.append(
            parse_lottery_gov_correct_score_text(
                text_path.read_text(encoding="utf-8"),
                snapshot_type=args.snapshot_type,
                captured_at=args.captured_at,
            )
        )

    output = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    output_path = _ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_path, index=False, encoding="utf-8-sig")

    audit = {
        "ok": True,
        "rows": int(len(output)),
        "play_type_counts": {
            str(key): int(value)
            for key, value in output.get("play_type", pd.Series(dtype=str))
            .value_counts()
            .sort_index()
            .items()
        },
        "matches": int(
            output[["date", "home_team", "away_team"]].drop_duplicates().shape[0]
        )
        if not output.empty
        else 0,
        "output": str(output_path),
    }
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
