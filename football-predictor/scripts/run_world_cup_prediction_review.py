from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.prediction_review import (
    attach_handicap_line_movement,
    build_chinese_review_report,
    build_review_group_stats,
    create_prediction_snapshot,
    load_enhanced_prediction_snapshot,
    load_espn_completed_results,
    settle_enhanced_predictions,
    summarize_enhanced_review,
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--predictions",
        default="artifacts/predictions/world_cup_lineup_adjusted_with_leisu_2026-06-16.csv",
    )
    parser.add_argument(
        "--scoreboard",
        default="data/external/espn-world-cup/scoreboard_2026.json",
    )
    parser.add_argument("--snapshot-date", default="2026-06-16")
    parser.add_argument(
        "--snapshot-dir",
        default="artifacts/prediction_snapshots",
    )
    parser.add_argument("--output-dir", default="artifacts/reviews")
    parser.add_argument(
        "--line-movement",
        default="",
        help="Optional Sporttery handicap line movement features CSV.",
    )
    args = parser.parse_args()

    snapshot_manifest = create_prediction_snapshot(
        _ROOT / args.predictions,
        _ROOT / args.snapshot_dir,
        snapshot_date=args.snapshot_date,
    )
    predictions = load_enhanced_prediction_snapshot(snapshot_manifest["snapshot_path"])
    results = load_espn_completed_results(_ROOT / args.scoreboard)
    settled = settle_enhanced_predictions(predictions, results)
    if args.line_movement:
        movement_path = _ROOT / args.line_movement
        if movement_path.exists():
            import pandas as pd

            settled = attach_handicap_line_movement(settled, pd.read_csv(movement_path))
    summary = summarize_enhanced_review(settled)
    summary["snapshot"] = snapshot_manifest

    output_dir = _ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = output_dir / f"world_cup_review_ledger_{args.snapshot_date}.csv"
    group_stats_path = output_dir / f"world_cup_review_group_stats_{args.snapshot_date}.csv"
    summary_path = output_dir / f"world_cup_review_summary_{args.snapshot_date}.json"
    report_path = output_dir / f"世界杯预测复盘_{args.snapshot_date}.md"
    settled.to_csv(ledger_path, index=False)
    group_stats = build_review_group_stats(settled)
    group_stats.to_csv(group_stats_path, index=False)
    summary["group_stats_output"] = str(group_stats_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report = build_chinese_review_report(settled, summary)
    report_path.write_text(report, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(str(ledger_path))
    print(str(group_stats_path))
    print(str(report_path))


if __name__ == "__main__":
    main()
