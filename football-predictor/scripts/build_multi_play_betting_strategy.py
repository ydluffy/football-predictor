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
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Build multi-play Sporttery betting candidates from SPF/RQSPF market snapshots."
    )
    parser.add_argument("--market-csv", required=True)
    parser.add_argument("--sales-day", default="", help="Filter kickoff to the Sporttery sales window, 10:00 through next-day 10:00.")
    parser.add_argument("--start-after", default="", help="Optional kickoff lower bound, e.g. 2026-07-14 11:00.")
    parser.add_argument("--start-before", default="", help="Optional kickoff upper bound, e.g. 2026-07-15 12:00.")
    parser.add_argument("--stake", type=float, default=100.0, help="Total stake per betting plan.")
    parser.add_argument("--max-matches", type=int, default=3, help="Legacy capacity hint; analysis always covers the entire filtered input batch.")
    parser.add_argument("--fixed-odds-min", type=float, default=6.00)
    parser.add_argument("--fixed-odds-max", type=float, default=10.00)
    parser.add_argument("--fixed-odds-target", type=float, default=8.00)
    parser.add_argument("--fixed-odds-max-legs", type=int, default=4)
    parser.add_argument(
        "--max-shared-production-matches",
        type=int,
        default=1,
        help="Maximum matches shared by SAFE and VALUE production plans; use 0 for the research-only independent-ticket candidate.",
    )
    parser.add_argument("--signal-csv", default="", help="Optional market signal feature CSV.")
    parser.add_argument("--handicap-model-csv", default="", help="Optional controlled handicap model predictions.")
    parser.add_argument("--plans-output", required=True)
    parser.add_argument("--matches-output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()

    market_path = _ROOT / args.market_csv
    markets = pd.read_csv(market_path).fillna("")
    if args.sales_day:
        if "kickoff_time" not in markets.columns:
            raise ValueError("market CSV has no kickoff_time column for --sales-day")
        sales_start = pd.Timestamp(args.sales_day) + pd.Timedelta(hours=10)
        sales_end = sales_start + pd.Timedelta(days=1)
        kickoff = pd.to_datetime(markets["kickoff_time"], errors="coerce")
        markets = markets[kickoff.ge(sales_start) & kickoff.lt(sales_end)].copy()
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
        max_matches=max(args.max_matches, len(markets)),
        fixed_odds_min=args.fixed_odds_min,
        fixed_odds_max=args.fixed_odds_max,
        fixed_odds_target=args.fixed_odds_target,
        fixed_odds_max_legs=args.fixed_odds_max_legs,
        max_shared_production_matches=args.max_shared_production_matches,
    )
    plans_frame = plans_to_frame(plans)
    matches_frame = pd.DataFrame(match_rows)

    def normalize_match_number(value: object) -> str:
        text = str(value).strip()
        return text.zfill(3) if text.isdigit() else text

    production_rejections: list[dict[str, object]] = []
    processed_numbers: set[str] = set()
    for _, row in matches_frame.iterrows():
        match_number = normalize_match_number(row.get("match_number", ""))
        processed_numbers.add(match_number)
        probability = float(row.get("favorite_probability", 0.0) or 0.0)
        odds = float(row.get("favorite_odds", 0.0) or 0.0)
        handicap_eligible = bool(row.get("handicap_production_eligible", False))
        spf_eligible = probability >= 0.52 and odds <= 1.85
        if spf_eligible or handicap_eligible:
            continue
        reasons: list[str] = []
        if probability < 0.52:
            reasons.append("favorite_probability_below_0.52")
        if odds > 1.85:
            reasons.append("favorite_odds_above_1.85")
        if not handicap_eligible:
            reasons.append("no_model_backed_handicap")
        production_rejections.append({
            "match_number": match_number,
            "match_name": row.get("match_name", ""),
            "favorite_probability": probability,
            "favorite_odds": odds,
            "reasons": reasons,
        })

    if "match_number" in markets.columns:
        for _, row in markets.iterrows():
            match_number = normalize_match_number(row.get("match_number", ""))
            if match_number and match_number not in processed_numbers:
                production_rejections.append({
                    "match_number": match_number,
                    "match_name": f'{row.get("home_team", "")} vs {row.get("away_team", "")}',
                    "reasons": ["incomplete_spf_or_rqspf_market"],
                })

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
        "production_rejections": production_rejections,
        "plans_output": str(plans_output),
        "matches_output": str(matches_output),
        "report_output": str(report_output),
    }
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit['quota_scope'] = 'sales_day_and_registered_batch'
    audit['formal_plan_cards'] = []
    for kind in ['稳健', '价值']:
        selected = plans_frame[plans_frame['plan_type'].eq(kind) & ~plans_frame['is_shadow'].astype(bool)] if not plans_frame.empty else plans_frame
        audit['formal_plan_cards'].append({
            'plan_type': kind, 'budget': 100, 'simulation_only': True,
            'status': 'candidate' if not selected.empty else 'not_generated',
            'reason': '' if not selected.empty else 'no_qualified_distinct_candidate',
            'valuation_status': 'market_structure_observation_not_validated_advantage' if kind == '价值' else 'relative_stability_not_principal_protection',
        })
    with report_output.open('a', encoding='utf-8') as handle:
        handle.write('\n\n每批模拟方案（每类预算上限100元；未使用预算保留）：\n')
        for card in audit['formal_plan_cards']:
            handle.write('\n- ' + card['plan_type'] + '：' + ('已有候选，须通过本批READY门禁后冻结入账。' if card['status'] == 'candidate' else '未生成；无合格且满足差异要求的候选，投入0元。'))
        handle.write('\n\n价值候选属于市场结构观察，不代表已验证正期望收益；稳健不代表保本。\n')
    audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
