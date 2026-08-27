from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from itertools import product
from math import prod
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.betting_strategy import BASE_BET_UNIT
from world_cup.betting_strategy import build_multi_play_plans
from world_cup.betting_strategy import plans_to_frame


TOTAL_GOAL_PRIORITY = {
    "low": ["1", "2", "3"],
    "balanced": ["2", "3", "1", "4"],
    "open": ["2", "3", "4", "5"],
}

SCORE_PRIORITY = {
    "low": ["1:1", "1:0", "0:1", "0:0"],
    "balanced": ["1:1", "2:1", "1:2", "1:0", "0:1"],
    "open": ["2:1", "1:2", "2:2", "3:1", "1:3"],
}

HALF_FULL_PRIORITY = {
    "low": ["D-D", "D-H", "D-A"],
    "balanced": ["D-D", "D-H", "D-A", "H-H", "A-A"],
    "open": ["H-H", "A-A", "D-H", "D-A"],
}


@dataclass(frozen=True)
class Candidate:
    plan_type: str
    play_type: str
    title: str
    selections: list[tuple[str, float]]
    note: str

    @property
    def bet_count(self) -> int:
        return len(self.selections)

    def multiplier(self, budget: float) -> int:
        if self.bet_count <= 0:
            return 0
        return int(budget // (self.bet_count * BASE_BET_UNIT))

    def total_stake(self, budget: float) -> float:
        return self.bet_count * BASE_BET_UNIT * self.multiplier(budget)

    def payout_range(self, budget: float) -> tuple[float, float]:
        multiplier = self.multiplier(budget)
        if multiplier <= 0:
            return 0.0, 0.0
        unit_stake = BASE_BET_UNIT * multiplier
        payouts = [unit_stake * odd for _, odd in self.selections]
        return min(payouts), max(payouts)


def _scenario(row: pd.Series) -> str:
    try:
        draw_odd = float(row.get("spf_odds_draw", 0) or 0)
        home_odd = float(row.get("spf_odds_home", 0) or 0)
        away_odd = float(row.get("spf_odds_away", 0) or 0)
    except ValueError:
        return "balanced"
    favorite = min(home_odd, away_odd)
    if draw_odd <= 3.1 or favorite >= 2.1:
        return "low"
    if favorite <= 1.55:
        return "open"
    return "balanced"


def _odds_for_match(play_odds: pd.DataFrame, row: pd.Series, play_type: str) -> dict[str, float]:
    frame = play_odds[
        play_odds["match_number"].astype(str).eq(str(row["match_number"]))
        & play_odds["home_team"].astype(str).eq(str(row["home_team"]))
        & play_odds["away_team"].astype(str).eq(str(row["away_team"]))
        & play_odds["play_type"].astype(str).eq(play_type)
    ]
    return {
        str(item["selection"]): float(item["odds"])
        for _, item in frame.iterrows()
        if str(item.get("odds", "")).strip()
    }


def _pick(odds: dict[str, float], priorities: list[str], count: int) -> list[tuple[str, float]]:
    picked = [(selection, odds[selection]) for selection in priorities if selection in odds]
    if len(picked) < count:
        remaining = sorted(
            [(selection, odd) for selection, odd in odds.items() if selection not in dict(picked)],
            key=lambda item: item[1],
        )
        picked.extend(remaining[: count - len(picked)])
    return picked[:count]


def _candidate_rows(candidates: list[Candidate], budget: float) -> pd.DataFrame:
    rows = []
    for candidate in candidates:
        payout_min, payout_max = candidate.payout_range(budget)
        total_stake = candidate.total_stake(budget)
        rows.append(
            {
                "plan_type": candidate.plan_type,
                "play_type": candidate.play_type,
                "title": candidate.title,
                "budget": budget,
                "bet_count": candidate.bet_count,
                "multiplier": candidate.multiplier(budget),
                "total_stake": round(total_stake, 2),
                "unused_budget": round(budget - total_stake, 2),
                "estimated_payout_min": round(payout_min, 2),
                "estimated_payout_max": round(payout_max, 2),
                "estimated_net_min": round(payout_min - total_stake, 2),
                "estimated_net_max": round(payout_max - total_stake, 2),
                "selections": " / ".join(f"{name}@{odd:g}" for name, odd in candidate.selections),
                "note": candidate.note,
            }
        )
    return pd.DataFrame(rows)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return ""
    lines = [
        "| " + " | ".join(str(column) for column in frame.columns) + " |",
        "| " + " | ".join("---" for _ in frame.columns) + " |",
    ]
    for row in frame.astype(str).itertuples(index=False, name=None):
        lines.append("| " + " | ".join(cell.replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)


def build_candidates(markets: pd.DataFrame, play_odds: pd.DataFrame, budget: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    base_markets = markets[
        pd.to_numeric(markets.get("spf_odds_home", ""), errors="coerce").gt(1)
        & pd.to_numeric(markets.get("spf_odds_draw", ""), errors="coerce").gt(1)
        & pd.to_numeric(markets.get("spf_odds_away", ""), errors="coerce").gt(1)
    ].copy()
    _, base_plans = build_multi_play_plans(base_markets, stake=budget, max_matches=len(base_markets))
    base_frame = plans_to_frame(base_plans)
    candidates: list[Candidate] = []

    for _, row in markets.iterrows():
        scenario = _scenario(row)
        match = f"{row['match_number']} {row['home_team']} vs {row['away_team']}"

        total_odds = _odds_for_match(play_odds, row, "total_goals")
        if total_odds:
            candidates.append(
                Candidate(
                    plan_type="总进球",
                    play_type="total_goals",
                    title=f"{match} 总进球双选",
                    selections=_pick(total_odds, TOTAL_GOAL_PRIORITY[scenario], 2),
                    note="单场多选，符合体彩规则；复盘需按90分钟总进球拆注结算。",
                )
            )

        score_odds = _odds_for_match(play_odds, row, "correct_score")
        if score_odds:
            candidates.append(
                Candidate(
                    plan_type="比分",
                    play_type="correct_score",
                    title=f"{match} 比分小额多选",
                    selections=_pick(score_odds, SCORE_PRIORITY[scenario], 3),
                    note="高赔率低命中玩法，只适合小额观察；不得与同场其他玩法混合过关。",
                )
            )

        half_full_odds = _odds_for_match(play_odds, row, "half_full_time")
        if half_full_odds:
            candidates.append(
                Candidate(
                    plan_type="半全场",
                    play_type="half_full_time",
                    title=f"{match} 半全场候选",
                    selections=_pick(half_full_odds, HALF_FULL_PRIORITY[scenario], 2),
                    note="用于验证半场脚本；不建议重仓。",
                )
            )

    return base_frame, _candidate_rows(candidates, budget)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-csv", required=True)
    parser.add_argument("--play-odds-csv", required=True)
    parser.add_argument("--start-after", required=True)
    parser.add_argument("--start-before", required=True)
    parser.add_argument("--budget", type=float, default=100.0)
    parser.add_argument("--base-output", required=True)
    parser.add_argument("--play-output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()

    markets = pd.read_csv(_ROOT / args.market_csv).fillna("")
    markets["kickoff_sort"] = pd.to_datetime(markets["kickoff_time"], errors="coerce")
    markets = markets[
        markets["kickoff_sort"].ge(pd.Timestamp(args.start_after))
        & markets["kickoff_sort"].le(pd.Timestamp(args.start_before))
    ].copy()
    markets = markets.sort_values(["kickoff_sort", "match_number"], kind="mergesort").drop(columns=["kickoff_sort"])
    play_odds = pd.read_csv(_ROOT / args.play_odds_csv).fillna("")

    base_frame, play_frame = build_candidates(markets, play_odds, args.budget)

    base_output = _ROOT / args.base_output
    play_output = _ROOT / args.play_output
    report_output = _ROOT / args.report_output
    audit_output = _ROOT / args.audit_output
    base_output.parent.mkdir(parents=True, exist_ok=True)
    play_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    base_frame.to_csv(base_output, index=False, encoding="utf-8-sig")
    play_frame.to_csv(play_output, index=False, encoding="utf-8-sig")

    lines = [
        "# 体彩全玩法候选方案",
        "",
        "说明：胜平负/让球方案可进入当前自动复盘账本；总进球、比分、半全场已抓到赔率，但需要拆注复盘器完整支持后再纳入ROI账本。",
        "",
        "## 胜平负/让球基础方案",
        "",
        _markdown_table(base_frame[["plan_type", "title", "stake", "bet_count", "total_stake", "estimated_payout_min", "estimated_payout_max", "selections"]]) if not base_frame.empty else "暂无。",
        "",
        "## 总进球/比分/半全场候选",
        "",
        _markdown_table(play_frame[["plan_type", "title", "budget", "bet_count", "multiplier", "total_stake", "estimated_payout_min", "estimated_payout_max", "selections", "note"]]) if not play_frame.empty else "暂无。",
        "",
        "## 规则提醒",
        "",
        "- 同一场比赛的不同玩法不能放进同一张混合过关方案。",
        "- 每个方案预算按100元以内控制，按2元基础注和整数倍计算。",
        "- 所有足球玩法均按90分钟含伤停补时结算。",
    ]
    report_output.write_text("\n".join(lines), encoding="utf-8")

    audit = {
        "ok": True,
        "market_rows": int(len(markets)),
        "base_plan_rows": int(len(base_frame)),
        "play_candidate_rows": int(len(play_frame)),
        "base_output": str(base_output),
        "play_output": str(play_output),
        "report_output": str(report_output),
    }
    audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
