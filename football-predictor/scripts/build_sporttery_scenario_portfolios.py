from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE_BET_UNIT = 2.0


@dataclass(frozen=True)
class Ticket:
    play_type: str
    title: str
    selections: list[tuple[str, float]]
    stake: float
    role: str

    @property
    def stake_per_selection(self) -> float:
        if not self.selections:
            return 0.0
        raw = self.stake / len(self.selections)
        return max(BASE_BET_UNIT, int(raw // BASE_BET_UNIT) * BASE_BET_UNIT)

    @property
    def actual_stake(self) -> float:
        return round(self.stake_per_selection * len(self.selections), 2)

    @property
    def payout_min(self) -> float:
        if not self.selections:
            return 0.0
        return round(min(odd for _, odd in self.selections) * self.stake_per_selection, 2)

    @property
    def payout_max(self) -> float:
        if not self.selections:
            return 0.0
        return round(max(odd for _, odd in self.selections) * self.stake_per_selection, 2)


def _num(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none", "null", "<na>"} else text


def _risk_flags(row: pd.Series) -> set[str]:
    return {flag for flag in _text(row.get("market_risk_flags")).split(",") if flag}


def _has_risk(row: pd.Series, *flags: str) -> bool:
    return bool(_risk_flags(row) & set(flags))


def _is_high_risk(row: pd.Series) -> bool:
    return _text(row.get("market_signal_strength")) == "high_risk"


def _play_odds(play_odds: pd.DataFrame, row: pd.Series, play_type: str) -> dict[str, float]:
    required = {"match_number", "home_team", "away_team", "play_type", "selection", "odds"}
    if play_odds.empty or not required.issubset(play_odds.columns):
        return {}
    matched = play_odds[
        play_odds["match_number"].astype(str).eq(str(row["match_number"]))
        & play_odds["home_team"].astype(str).eq(str(row["home_team"]))
        & play_odds["away_team"].astype(str).eq(str(row["away_team"]))
        & play_odds["play_type"].astype(str).eq(play_type)
    ]
    return {str(item["selection"]): _num(item["odds"]) for _, item in matched.iterrows() if _num(item["odds"]) > 0}


def _pick(odds: dict[str, float], priorities: list[str], count: int) -> list[tuple[str, float]]:
    picked = [(key, odds[key]) for key in priorities if key in odds]
    if len(picked) < count:
        picked.extend(
            sorted(
                [(key, odd) for key, odd in odds.items() if key not in {p[0] for p in picked}],
                key=lambda item: item[1],
            )[: count - len(picked)]
        )
    return picked[:count]


def _favorite_side(row: pd.Series) -> str:
    home = _num(row.get("spf_odds_home"))
    draw = _num(row.get("spf_odds_draw"))
    away = _num(row.get("spf_odds_away"))
    values = {"home": home, "draw": draw, "away": away}
    return min(values, key=values.get) if all(values.values()) else "draw"


def _score_priorities(row: pd.Series, scenario: str) -> list[str]:
    if _has_risk(row, "deep_line_but_under_signal"):
        return ["1:0", "1:1", "0:0", "2:0", "2:1", "0:1"]
    if _has_risk(row, "sporttery_deeper_than_external", "external_shallow_vs_sporttery_deep"):
        if scenario == "home":
            return ["1:0", "2:1", "1:1", "0:0", "2:0", "0:1"]
        if scenario == "away":
            return ["0:1", "1:2", "1:1", "0:0", "0:2", "1:0"]
    if scenario == "home":
        return ["1:1", "0:1", "1:2", "0:2", "1:0", "2:1"]
    if scenario == "away":
        return ["1:1", "1:0", "2:1", "2:0", "0:1", "1:2"]
    return ["1:1", "0:0", "1:0", "0:1", "2:2"]


def _total_priorities(row: pd.Series) -> list[str]:
    if _text(row.get("external_latest_total_signal")) == "under" or _has_risk(row, "deep_line_but_under_signal"):
        return ["1", "2", "0", "3"]
    if _text(row.get("external_latest_total_signal")) == "over":
        return ["2", "3", "4", "1"]
    draw = _num(row.get("spf_odds_draw"))
    favorite = min(_num(row.get("spf_odds_home"), 99), _num(row.get("spf_odds_away"), 99))
    if draw <= 3.1 or favorite >= 2.1:
        return ["1", "2", "0", "3"]
    return ["2", "3", "1", "4"]


def _half_full_priorities(row: pd.Series, scenario: str) -> list[str]:
    if _has_risk(row, "deep_line_but_under_signal"):
        return ["D-D", "D-H", "H-H"] if scenario == "home" else ["D-D", "D-A", "A-A"]
    if _has_risk(row, "sporttery_deeper_than_external", "external_shallow_vs_sporttery_deep"):
        return ["D-H", "D-D", "H-H"] if scenario == "home" else ["D-A", "D-D", "A-A"]
    if scenario == "home":
        return ["D-H", "H-H", "D-D"]
    if scenario == "away":
        return ["D-A", "A-A", "D-D"]
    return ["D-D", "D-H", "D-A"]


def _direction_ticket(row: pd.Series, scenario: str) -> Ticket:
    stake = 18 if _is_high_risk(row) else 28
    if scenario == "home":
        return Ticket("spf", "胜平负主方向", [("胜", _num(row["spf_odds_home"]))], stake, "主判断")
    if scenario == "away":
        return Ticket("spf", "胜平负主方向", [("负", _num(row["spf_odds_away"]))], stake, "主判断")
    return Ticket("spf", "胜平负主方向", [("平", _num(row["spf_odds_draw"]))], stake, "主判断")


def _handicap_ticket(row: pd.Series, scenario: str) -> Ticket:
    handicap = int(str(row.get("home_handicap") or "0").replace("+", ""))
    home = str(row["home_team"])
    if handicap > 0:
        if scenario == "away":
            priorities = [("让负", _num(row["rqspf_odds_away"])), ("让平", _num(row["rqspf_odds_draw"]))]
            role = "客队强势防线：重点防客队赢两球/赢一球"
        else:
            priorities = [("让胜", _num(row["rqspf_odds_home"])), ("让平", _num(row["rqspf_odds_draw"]))]
            role = "受让方防线：重点防不败/输一球"
    elif handicap < 0:
        priorities = [("让负", _num(row["rqspf_odds_away"])), ("让平", _num(row["rqspf_odds_draw"]))]
        role = "热门让球防线：重点防赢球不穿/爆冷"
    else:
        priorities = [("让平", _num(row["rqspf_odds_draw"]))]
        role = "平手盘防线"
    stake = 24 if _has_risk(row, "sporttery_deeper_than_external", "external_shallow_vs_sporttery_deep") else 20
    return Ticket("rqspf", f"{home}{handicap:+d}让球防线", priorities[:2], stake, role)


def _ticket_text(ticket: Ticket) -> str:
    choices = "/".join(f"{selection}@{odd:g}" for selection, odd in ticket.selections)
    return (
        f"{ticket.role}｜{ticket.title}｜{choices}｜"
        f"{ticket.actual_stake:g}元({ticket.stake_per_selection:g}元/项)｜"
        f"返奖区间{ticket.payout_min:g}-{ticket.payout_max:g}"
    )


def _clean_ticket(ticket: Ticket) -> Ticket:
    return Ticket(
        ticket.play_type,
        ticket.title,
        [(selection, odd) for selection, odd in ticket.selections if odd > 1.0],
        ticket.stake,
        ticket.role,
    )


def merge_signal_features(markets: pd.DataFrame, signal_csv: str) -> pd.DataFrame:
    if not signal_csv:
        return markets
    signal_path = ROOT / signal_csv
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


def build_portfolios(markets: pd.DataFrame, play_odds: pd.DataFrame, budget: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, row in markets.iterrows():
        scenario = _favorite_side(row)
        total_odds = _play_odds(play_odds, row, "total_goals")
        score_odds = _play_odds(play_odds, row, "correct_score")
        half_full_odds = _play_odds(play_odds, row, "half_full_time")

        tickets = [
            _direction_ticket(row, scenario),
            _handicap_ticket(row, scenario),
            Ticket(
                "total_goals",
                "总进球双选",
                _pick(total_odds, _total_priorities(row), 2),
                24,
                "节奏覆盖",
            ),
            Ticket(
                "correct_score",
                "比分防冷多选",
                _pick(score_odds, _score_priorities(row, scenario), 3),
                20 if _is_high_risk(row) else 18,
                "精确比分/冷门补偿",
            ),
            Ticket(
                "half_full_time",
                "半全场进程",
                _pick(half_full_odds, _half_full_priorities(row, scenario), 2),
                10,
                "比赛进程覆盖",
            ),
        ]
        tickets = [_clean_ticket(ticket) for ticket in tickets]
        tickets = [ticket for ticket in tickets if ticket.selections]
        total_stake = round(sum(ticket.actual_stake for ticket in tickets), 2)
        if total_stake > budget:
            # Keep the core layers first if rounding ever pushes the package over budget.
            while tickets and total_stake > budget:
                tickets.pop()
                total_stake = round(sum(ticket.actual_stake for ticket in tickets), 2)

        rows.append(
            {
                "plan_id": f"SCENARIO_{row['match_number']}",
                "match_number": row["match_number"],
                "kickoff_time": row["kickoff_time"],
                "match": f"{row['home_team']} vs {row['away_team']}",
                "scenario": {"home": "主队方向", "away": "客队方向", "draw": "平局方向"}[scenario],
                "market_signal_strength": _text(row.get("market_signal_strength")),
                "market_risk_flags": _text(row.get("market_risk_flags")),
                "market_signal_note": _text(row.get("market_signal_note")),
                "budget": budget,
                "total_stake": total_stake,
                "unused_budget": round(budget - total_stake, 2),
                "ticket_count": len(tickets),
                "estimated_payout_min": round(min(ticket.payout_min for ticket in tickets), 2) if tickets else 0,
                "estimated_payout_max": round(max(ticket.payout_max for ticket in tickets), 2) if tickets else 0,
                "tickets": "；".join(_ticket_text(ticket) for ticket in tickets),
                "note": "同场剧本方案包：不是串成一张票，而是在100元内拆成主判断、防线、进球数、比分、半全场，赛后看哪一层救回成本。",
            }
        )
    return pd.DataFrame(rows)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "暂无。"
    columns = [
        "match_number",
        "kickoff_time",
        "match",
        "scenario",
        "market_signal_strength",
        "market_signal_note",
        "total_stake",
        "estimated_payout_min",
        "estimated_payout_max",
        "tickets",
    ]
    view = frame[[column for column in columns if column in frame.columns]].copy()
    lines = [
        "| " + " | ".join(view.columns) + " |",
        "| " + " | ".join("---" for _ in view.columns) + " |",
    ]
    for row in view.astype(str).itertuples(index=False, name=None):
        lines.append("| " + " | ".join(cell.replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-csv", required=True)
    parser.add_argument("--play-odds-csv", required=True)
    parser.add_argument("--signal-csv", default="", help="Optional market signal feature CSV.")
    parser.add_argument("--start-after", required=True)
    parser.add_argument("--start-before", required=True)
    parser.add_argument("--budget", type=float, default=100.0)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()

    markets = pd.read_csv(ROOT / args.market_csv).fillna("")
    markets = merge_signal_features(markets, args.signal_csv)
    markets["kickoff_sort"] = pd.to_datetime(markets["kickoff_time"], errors="coerce")
    markets = markets[
        markets["kickoff_sort"].ge(pd.Timestamp(args.start_after))
        & markets["kickoff_sort"].le(pd.Timestamp(args.start_before))
    ].copy()
    markets = markets.sort_values(["kickoff_sort", "match_number"], kind="mergesort").drop(columns=["kickoff_sort"])
    play_odds = pd.read_csv(ROOT / args.play_odds_csv).fillna("")

    frame = build_portfolios(markets, play_odds, args.budget)
    output = ROOT / args.output
    report_output = ROOT / args.report_output
    audit_output = ROOT / args.audit_output
    output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False, encoding="utf-8-sig")
    report_output.write_text(
        "# 体彩同场剧本组合投注候选\n\n"
        "说明：本报告按每场100元以内拆分，不是把同一场不同玩法强行混成一张串关票。"
        "它用于回答“主判断之外，比分、进球数、半全场如何防冷/补偿”的问题。\n\n"
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
