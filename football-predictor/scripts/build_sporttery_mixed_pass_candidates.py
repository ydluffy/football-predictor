from __future__ import annotations

import argparse
import json
from itertools import product
from math import prod
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE_BET_UNIT = 2.0


def _budget_stats(bet_count: int, budget: float) -> dict[str, float | int]:
    multiplier = int(budget // (bet_count * BASE_BET_UNIT)) if bet_count else 0
    total_stake = bet_count * BASE_BET_UNIT * multiplier
    return {
        "bet_count": bet_count,
        "multiplier": multiplier,
        "total_stake": round(total_stake, 2),
        "unused_budget": round(budget - total_stake, 2),
        "unit_stake": round(BASE_BET_UNIT * multiplier, 2),
    }


def _payout_range(legs: list[list[tuple[str, float]]], unit_stake: float) -> tuple[float, float]:
    payouts = []
    for combination in product(*legs):
        payouts.append(unit_stake * prod(float(odd) for _, odd in combination))
    return (min(payouts), max(payouts)) if payouts else (0.0, 0.0)


def _play_odds(play_odds: pd.DataFrame, row: pd.Series, play_type: str) -> dict[str, float]:
    matched = play_odds[
        play_odds["match_number"].astype(str).eq(str(row["match_number"]))
        & play_odds["home_team"].astype(str).eq(str(row["home_team"]))
        & play_odds["away_team"].astype(str).eq(str(row["away_team"]))
        & play_odds["play_type"].astype(str).eq(play_type)
    ]
    return {str(item["selection"]): float(item["odds"]) for _, item in matched.iterrows()}


def _pick(odds: dict[str, float], priorities: list[str], count: int = 1) -> list[tuple[str, float]]:
    picked = [(key, odds[key]) for key in priorities if key in odds]
    if len(picked) < count:
        picked.extend(
            sorted(
                [(key, odd) for key, odd in odds.items() if key not in dict(picked)],
                key=lambda item: item[1],
            )[: count - len(picked)]
        )
    return picked[:count]


def _rqspf_choice(row: pd.Series, key: str | None = None) -> tuple[str, float]:
    handicap = str(row["home_handicap"])
    choices = {
        "让胜": float(row["rqspf_odds_home"]),
        "让平": float(row["rqspf_odds_draw"]),
        "让负": float(row["rqspf_odds_away"]),
    }
    if key and key in choices:
        return f"{row['match_number']} {row['home_team']}{handicap}{key}", choices[key]
    label, odd = min(choices.items(), key=lambda item: item[1])
    return f"{row['match_number']} {row['home_team']}{handicap}{label}", odd


def _leg_text(legs: list[tuple[str, list[tuple[str, float]]]]) -> str:
    return " + ".join(
        f"{name}({('/'.join(f'{selection}@{odd:g}' for selection, odd in choices))})"
        for name, choices in legs
    )


def build_mixed(markets: pd.DataFrame, play_odds: pd.DataFrame, budget: float) -> pd.DataFrame:
    markets = markets.copy()
    rows = list(markets.iterrows())
    if len(rows) < 2:
        return pd.DataFrame()
    ordered = [row for _, row in rows]
    candidates = []

    # Cross-match mixed pass: never uses two play types from the same match.
    first = ordered[0]
    second = ordered[1]
    second_total = _pick(_play_odds(play_odds, second, "total_goals"), ["1", "2", "3"], 1)
    if second_total:
        legs = [
            (f"{first['match_number']} {first['home_team']} vs {first['away_team']} 让球", [_rqspf_choice(first)]),
            (f"{second['match_number']} {second['home_team']} vs {second['away_team']} 总进球", second_total),
        ]
        candidates.append(("混合稳健2串", legs, "跨场：让球 + 总进球。"))

    if len(ordered) >= 3:
        third = ordered[2]
        first_total = _pick(_play_odds(play_odds, first, "total_goals"), ["1", "2", "3"], 1)
        second_half = _pick(_play_odds(play_odds, second, "half_full_time"), ["D-D", "D-H", "D-A"], 1)
        if first_total and second_half:
            legs = [
                (f"{first['match_number']} {first['home_team']} vs {first['away_team']} 总进球", first_total),
                (f"{second['match_number']} {second['home_team']} vs {second['away_team']} 半全场", second_half),
                (f"{third['match_number']} {third['home_team']} vs {third['away_team']} 让球", [_rqspf_choice(third)]),
            ]
            candidates.append(("混合价值3串", legs, "跨场三玩法：总进球 + 半全场 + 让球。"))

        third_score = _pick(_play_odds(play_odds, third, "correct_score"), ["1:1", "2:1", "1:2"], 1)
        if third_score:
            legs = [
                (f"{first['match_number']} {first['home_team']} vs {first['away_team']} 让球", [_rqspf_choice(first)]),
                (f"{second['match_number']} {second['home_team']} vs {second['away_team']} 总进球", second_total or []),
                (f"{third['match_number']} {third['home_team']} vs {third['away_team']} 比分", third_score),
            ]
            if all(choices for _, choices in legs):
                candidates.append(("混合博高3串", legs, "跨场：让球 + 总进球 + 比分，高风险观察。"))

    out = []
    for title, legs, note in candidates:
        leg_choices = [choices for _, choices in legs]
        bet_count = int(prod(len(choices) for choices in leg_choices))
        stats = _budget_stats(bet_count, budget)
        payout_min, payout_max = _payout_range(leg_choices, float(stats["unit_stake"]))
        out.append(
            {
                "plan_type": "混合过关",
                "title": title,
                "budget": budget,
                **stats,
                "estimated_payout_min": round(payout_min, 2),
                "estimated_payout_max": round(payout_max, 2),
                "estimated_net_min": round(payout_min - float(stats["total_stake"]), 2),
                "estimated_net_max": round(payout_max - float(stats["total_stake"]), 2),
                "selections": _leg_text(legs),
                "note": note + " 同一场不同玩法不混在同一张方案。",
            }
        )
    return pd.DataFrame(out)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "暂无。"
    lines = [
        "| " + " | ".join(str(column) for column in frame.columns) + " |",
        "| " + " | ".join("---" for _ in frame.columns) + " |",
    ]
    for row in frame.astype(str).itertuples(index=False, name=None):
        lines.append("| " + " | ".join(cell.replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-csv", required=True)
    parser.add_argument("--play-odds-csv", required=True)
    parser.add_argument("--start-after", required=True)
    parser.add_argument("--start-before", required=True)
    parser.add_argument("--budget", type=float, default=100.0)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()

    markets = pd.read_csv(ROOT / args.market_csv).fillna("")
    markets["kickoff_sort"] = pd.to_datetime(markets["kickoff_time"], errors="coerce")
    markets = markets[
        markets["kickoff_sort"].ge(pd.Timestamp(args.start_after))
        & markets["kickoff_sort"].le(pd.Timestamp(args.start_before))
    ].copy()
    markets = markets.sort_values(["kickoff_sort", "match_number"], kind="mergesort").drop(columns=["kickoff_sort"])
    play_odds = pd.read_csv(ROOT / args.play_odds_csv).fillna("")

    frame = build_mixed(markets, play_odds, args.budget)
    output = ROOT / args.output
    report_output = ROOT / args.report_output
    audit_output = ROOT / args.audit_output
    output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False, encoding="utf-8-sig")
    report_output.write_text(
        "# 体彩跨场混合过关候选\n\n"
        "说明：混合过关可以跨场混不同玩法；本报告避免同一场比赛多个玩法进入同一方案。\n\n"
        + _markdown_table(frame)
        + "\n",
        encoding="utf-8",
    )
    audit = {
        "ok": True,
        "rows": int(len(frame)),
        "output": str(output),
        "report_output": str(report_output),
    }
    audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
