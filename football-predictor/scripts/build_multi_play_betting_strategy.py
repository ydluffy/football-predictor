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

from world_cup.betting_strategy import build_multi_play_plans
from world_cup.betting_strategy import plans_to_frame
from world_cup.betting_strategy import write_multi_play_report


def merge_signal_features(markets: pd.DataFrame, signal_csv: str) -> pd.DataFrame:
    if not signal_csv:
        return markets
    signal_path = _ROOT / signal_csv
    if not signal_path.exists():
        return markets
    signals = pd.read_csv(signal_path).fillna("")
    keys = [key for key in ["date", "match_number", "home_team", "away_team"] if key in markets.columns and key in signals.columns]
    if not keys:
        keys = [key for key in ["match_number", "home_team", "away_team"] if key in markets.columns and key in signals.columns]
    signal_columns = [
        "market_signal_strength",
        "market_risk_flags",
        "market_signal_note",
        "inner_outer_home_line_gap",
        "inner_outer_line_relation",
        "external_latest_home_spread_point",
        "external_latest_total_signal",
    ]
    available_columns = keys + [column for column in signal_columns if column in signals.columns]
    if not keys or len(available_columns) == len(keys):
        return markets
    return markets.merge(signals[available_columns].drop_duplicates(keys), on=keys, how="left")


def merge_handicap_model_features(markets: pd.DataFrame, prediction_csv: str) -> pd.DataFrame:
    if not prediction_csv:
        return markets
    prediction_path = _ROOT / prediction_csv
    if not prediction_path.exists():
        return markets
    predictions = pd.read_csv(prediction_path).fillna("")
    keys = [
        key for key in ["date", "match_number", "home_team", "away_team"]
        if key in markets.columns and key in predictions.columns
    ]
    if not keys:
        return markets
    columns = [
        "handicap_model_usage", "handicap_model_reason", "handicap_model_weight",
        "handicap_model_probability_home", "handicap_model_probability_draw", "handicap_model_probability_away",
        "handicap_blended_probability_home", "handicap_blended_probability_draw", "handicap_blended_probability_away",
        "handicap_model_pick", "handicap_model_edge", "handicap_model_expected_value",
        "handicap_model_external_line", "handicap_model_source_captured_at", "handicap_model_id",
    ]
    available = keys + [column for column in columns if column in predictions.columns]
    return markets.merge(predictions[available].drop_duplicates(keys), on=keys, how="left")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build multi-play Sporttery betting candidates from SPF/RQSPF market snapshots."
    )
    parser.add_argument("--market-csv", required=True)
    parser.add_argument("--start-after", default="", help="Optional kickoff lower bound, e.g. 2026-07-14 11:00.")
    parser.add_argument("--start-before", default="", help="Optional kickoff upper bound, e.g. 2026-07-15 12:00.")
    parser.add_argument("--stake", type=float, default=100.0, help="Total stake per betting plan.")
    parser.add_argument("--max-matches", type=int, default=3)
    parser.add_argument("--fixed-odds-min", type=float, default=6.00)
    parser.add_argument("--fixed-odds-max", type=float, default=10.00)
    parser.add_argument("--fixed-odds-target", type=float, default=8.00)
    parser.add_argument("--fixed-odds-max-legs", type=int, default=4)
    parser.add_argument("--signal-csv", default="", help="Optional market signal feature CSV.")
    parser.add_argument("--handicap-model-csv", default="", help="Optional controlled handicap model predictions.")
    parser.add_argument("--plans-output", required=True)
    parser.add_argument("--matches-output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()

    market_path = _ROOT / args.market_csv
    markets = pd.read_csv(market_path).fillna("")
    markets = merge_signal_features(markets, args.signal_csv)
    markets = merge_handicap_model_features(markets, args.handicap_model_csv)
    if not markets.empty and "kickoff_time" in markets.columns:
        markets["kickoff_sort"] = pd.to_datetime(markets["kickoff_time"], errors="coerce")
        if args.start_after:
            markets = markets[markets["kickoff_sort"].ge(pd.Timestamp(args.start_after))]
        if args.start_before:
            markets = markets[markets["kickoff_sort"].le(pd.Timestamp(args.start_before))]
        markets = markets.sort_values(["kickoff_sort", "match_number"], kind="mergesort")
        markets = markets.drop(columns=["kickoff_sort"])

    match_rows, plans = build_multi_play_plans(
        markets,
        stake=args.stake,
        max_matches=args.max_matches,
        fixed_odds_min=args.fixed_odds_min,
        fixed_odds_max=args.fixed_odds_max,
        fixed_odds_target=args.fixed_odds_target,
        fixed_odds_max_legs=args.fixed_odds_max_legs,
    )
    plans_frame = plans_to_frame(plans)
    matches_frame = pd.DataFrame(match_rows)

    plans_output = _ROOT / args.plans_output
    matches_output = _ROOT / args.matches_output
    report_output = _ROOT / args.report_output
    audit_output = _ROOT / args.audit_output

    plans_output.parent.mkdir(parents=True, exist_ok=True)
    matches_output.parent.mkdir(parents=True, exist_ok=True)
    plans_frame.to_csv(plans_output, index=False, encoding="utf-8-sig")
    matches_frame.to_csv(matches_output, index=False, encoding="utf-8-sig")
    write_multi_play_report(
        match_rows=match_rows,
        plans=plans,
        output_path=report_output,
        title="体彩多玩法投注策略候选",
    )

    audit = {
        "ok": True,
        "market_csv": str(market_path),
        "input_rows": int(len(markets)),
        "match_rows": int(len(matches_frame)),
        "plan_rows": int(len(plans_frame)),
        "production_plan_rows": int((~plans_frame.get("is_shadow", pd.Series(dtype=bool)).astype(bool)).sum()) if not plans_frame.empty else 0,
        "shadow_plan_rows": int(plans_frame.get("is_shadow", pd.Series(dtype=bool)).astype(bool).sum()) if not plans_frame.empty else 0,
        "fixed_odds": {
            "minimum": args.fixed_odds_min,
            "maximum": args.fixed_odds_max,
            "target": args.fixed_odds_target,
            "max_legs": args.fixed_odds_max_legs,
            "plan_generated": bool(
                not plans_frame.empty
                and plans_frame["plan_type"].astype(str).eq("固定赔率观察").any()
            ),
        },
        "handicap_model_rows": int(markets.get("handicap_model_usage", pd.Series(dtype=str)).astype(str).isin(["production_auxiliary", "limited_auxiliary"]).sum()),
        "plans_output": str(plans_output),
        "matches_output": str(matches_output),
        "report_output": str(report_output),
    }
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
