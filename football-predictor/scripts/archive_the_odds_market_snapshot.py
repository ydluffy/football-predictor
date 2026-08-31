from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from research_inner_outer_market_patterns import build_external_features


ROOT = Path(__file__).resolve().parents[1]


def _timestamp(value: str) -> str:
    if value:
        parsed = pd.Timestamp(value)
    else:
        parsed = pd.Timestamp(datetime.now(timezone.utc))
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC").strftime("%Y%m%dT%H%M%SZ")


def archive_snapshot(
    odds_path: Path,
    summary_path: Path,
    snapshot_dir: Path,
    history_path: Path,
    *,
    captured_at: str,
    snapshot_type: str,
) -> dict[str, object]:
    if not odds_path.exists():
        raise FileNotFoundError(f"missing odds file: {odds_path}")
    stamp = _timestamp(captured_at)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    odds_snapshot = snapshot_dir / f"the_odds_api_odds_{stamp}_{snapshot_type}.csv"
    shutil.copy2(odds_path, odds_snapshot)
    summary_snapshot = ""
    if summary_path.exists():
        summary_output = snapshot_dir / f"the_odds_api_market_summary_{stamp}_{snapshot_type}.csv"
        shutil.copy2(summary_path, summary_output)
        summary_snapshot = str(summary_output)

    odds = pd.read_csv(odds_path).fillna("")
    features = build_external_features(odds)
    features["snapshot_type"] = snapshot_type
    features["captured_at"] = pd.Timestamp(captured_at or datetime.now(timezone.utc)).isoformat()
    features["odds_snapshot"] = str(odds_snapshot)
    features["summary_snapshot"] = summary_snapshot

    if history_path.exists():
        history = pd.read_csv(history_path).fillna("")
        combined = pd.concat([history, features], ignore_index=True, sort=False)
    else:
        combined = features
    history_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(history_path, index=False, encoding="utf-8-sig")
    return {
        "ok": True,
        "odds_snapshot": str(odds_snapshot),
        "summary_snapshot": summary_snapshot,
        "history_output": str(history_path),
        "snapshot_rows": int(len(features)),
        "history_rows": int(len(combined)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive The Odds API market files into append-only snapshots.")
    parser.add_argument("--odds", default="data/external/the_odds_api_world_cup/odds.csv")
    parser.add_argument("--summary", default="data/external/the_odds_api_world_cup/match_market_summary.csv")
    parser.add_argument("--snapshot-dir", default="data/external/the_odds_api_world_cup/snapshots")
    parser.add_argument("--history-output", default="data/manual/external_market_snapshot_history.csv")
    parser.add_argument("--captured-at", default="")
    parser.add_argument("--snapshot-type", default="manual")
    args = parser.parse_args()

    audit = archive_snapshot(
        ROOT / args.odds,
        ROOT / args.summary,
        ROOT / args.snapshot_dir,
        ROOT / args.history_output,
        captured_at=args.captured_at,
        snapshot_type=args.snapshot_type,
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
