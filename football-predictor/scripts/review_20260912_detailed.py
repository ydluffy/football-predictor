"""Reconcile the frozen 2026-09-12 predictions and shadow schemes against official results."""
from __future__ import annotations

import csv
import itertools
import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-12"
DATA = ROOT / "artifacts/data"
PICKS = ("1408_001-002", "1642_003-004", "1845_005-030")


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def score_parts(score: str) -> tuple[int, int]:
    left, right = score.split(":")
    return int(left), int(right)


def side(score: str) -> str:
    home, away = score_parts(score)
    return "H" if home > away else "D" if home == away else "A"


def actuals(row: dict) -> dict:
    home, away = score_parts(row["full_time_score"])
    return {
        "spf": {"H": "主胜", "D": "平", "A": "客胜"}[side(row["full_time_score"])],
        "rq": row["rqspf_result"],
        "goals": str(min(home + away, 7)) if home + away < 7 else "7+",
        "score": row["full_time_score"],
        "half_full": f"{side(row['half_time_score'])}-{side(row['full_time_score'])}",
    }


def labels(items: list) -> list[str]:
    return [str(item[0] if isinstance(item, list) else item).replace("：", ":") for item in items]


def odds_map(predictions: dict[str, dict]) -> dict[tuple[str, str, str], float]:
    result = {}
    for number, prediction in predictions.items():
        for key, odds in prediction.get("spf", {}).items():
            if odds:
                result[(number, "spf", key)] = float(odds)
    for row in rows(ROOT / "data/manual/sporttery_play_odds_2026-09-12_1832_confirm.csv"):
        if row["play_type"] == "total_goals" and row["odds"]:
            result[(row["match_number"], "goals", row["selection"])] = float(row["odds"])
    return result


def leg(number: str, market: str, pick: str, odd: float | None, actual: dict) -> dict:
    if market == "spf":
        wanted = {"H": "主胜", "D": "平", "A": "客胜"}[pick]
        hit = actual["spf"] == wanted
    elif market == "rq":
        wanted = pick
        hit = actual["rq"] == wanted
    else:
        wanted = pick
        hit = actual["goals"] == wanted
    return {"number": number, "market": market, "pick": wanted, "odds": odd,
            "actual": actual[market], "hit": hit}


def settle_scheme(name: str, selection: str, stake: float, predictions: dict,
                  actual_by_number: dict, odds: dict) -> dict:
    tickets: list[list[dict]] = []
    if name == "防冷复式":
        for first, second in itertools.product(("H", "A"), ("A", "H")):
            tickets.append([leg(number, "spf", pick, odds.get((number, "spf", pick)), actual_by_number[number])
                            for number, pick in (("013", first), ("005", second))])
    elif name == "进球格局":
        for choices in itertools.product(("3", "2"), ("2", "3"), ("3", "4")):
            tickets.append([leg(number, "goals", pick, odds.get((number, "goals", pick)), actual_by_number[number])
                            for number, pick in zip(("005", "006", "007"), choices)])
    else:
        found = re.findall(r"(\d{3})(?:[+-]\d)?(主胜|客胜|平|让平)@([\d.]+)", selection)
        if not found:
            raise ValueError(f"unparseable frozen scheme: {name}")
        ticket = []
        for number, choice, odd in found:
            market = "rq" if choice.startswith("让") else "spf"
            pick = {"主胜": "H", "客胜": "A", "平": "D"}.get(choice, choice)
            ticket.append(leg(number, market, pick, float(odd), actual_by_number[number]))
        tickets.append(ticket)
    unit = stake / len(tickets)
    details = []
    payout = 0.0
    for ticket in tickets:
        if any(item["odds"] is None for item in ticket):
            raise ValueError(f"missing frozen odds for {name}")
        hit = all(item["hit"] for item in ticket)
        prize = round(unit * math.prod(item["odds"] for item in ticket), 2) if hit else 0.0
        payout += prize
        details.append({"stake": unit, "hit": hit, "payout": prize, "legs": ticket})
    payout = round(payout, 2)
    net = round(payout - stake, 2)
    return {"name": name, "selection": selection, "stake": stake, "ticket_count": len(tickets),
            "hit_tickets": sum(item["hit"] for item in details), "payout": payout, "net": net,
            "roi": round(net / stake, 6), "tickets": details}


def main() -> None:
    source = [json.loads((DATA / f"sporttery_final_analysis_{DAY}_{name}.json").read_text(encoding="utf-8"))
              for name in PICKS]
    official = {row["match_number"][-3:]: row for row in rows(ROOT / "data/manual/sporttery_results_2026-09-12_sales_window.csv")
                if row["match_number"].startswith("周六")}
    assert set(official) == {f"{number:03d}" for number in range(1, 31)}
    assert all(row["status"] == "已完成" and row["full_time_score"] and row["half_time_score"] for row in official.values())
    predictions = {}
    for batch in source:
        for prediction in batch["predictions"]:
            number = prediction.get("match_number") or prediction.get("number")
            assert number not in predictions
            predictions[number] = prediction
    assert set(predictions) == set(official)
    actual_by_number = {number: actuals(row) for number, row in official.items()}
    metrics = Counter()
    per_match = []
    for number in sorted(predictions):
        prediction, official_row, actual = predictions[number], official[number], actual_by_number[number]
        spf_open = prediction.get("spf_available", True)
        primary = prediction["primary"]
        defense = prediction.get("defense", "")
        rq_primary = prediction.get("rq_primary") or prediction.get("handicap_primary")
        rq_defense = prediction.get("rq_defense") or prediction.get("handicap_defense")
        goals, scores, half_full = (labels(prediction.get(key, [])) for key in ("goals", "scores", "half_full"))
        if spf_open:
            metrics["spf_total"] += 1
            metrics["spf_primary_hits"] += primary == actual["spf"]
            metrics["spf_covered_hits"] += actual["spf"] in {primary, defense}
        metrics["rq_total"] += 1
        metrics["rq_primary_hits"] += rq_primary == actual["rq"]
        metrics["rq_covered_hits"] += actual["rq"] in {rq_primary, rq_defense}
        for market, offered, winning in (("goals", goals, actual["goals"]),
                                         ("score", scores, actual["score"]),
                                         ("half_full", half_full, actual["half_full"])):
            if offered:
                metrics[f"{market}_total"] += 1
                metrics[f"{market}_covered_hits"] += winning in offered
        per_match.append({"number": number, "competition": official_row["competition"],
                          "home": official_row["home_team"], "away": official_row["away_team"],
                          "half_time": official_row["half_time_score"], "full_time": official_row["full_time_score"],
                          "handicap": official_row["handicap"], "actual": actual,
                          "spf_open": spf_open, "primary": primary, "defense": defense,
                          "rq_primary": rq_primary, "rq_defense": rq_defense,
                          "goals": goals, "scores": scores, "half_full": half_full,
                          "contrarian": prediction.get("contrarian", ""),
                          "model_note": prediction.get("model_note", "")})
    formal = [row for row in rows(ROOT / "data/manual/betting_plan_ledger.csv") if row["date"] == DAY]
    fixed = [row for row in rows(ROOT / "data/manual/fixed_odds_shadow_ledger.csv") if row["date"] == DAY]
    assert len(formal) == 2 and len(fixed) == 3
    assert all(row["result"] in {"命中", "未中"} for row in formal + fixed)
    shadow = [settle_scheme(item["name"], item["selection"], float(item["stake"]),
                            predictions, actual_by_number, odds_map(predictions))
              for item in source[2]["shadow_schemes"]]
    report = {"sales_day": DAY, "status": "completed_local_only", "official_matches": 30,
              "all_finished": True, "metrics": dict(metrics), "per_match": per_match,
              "formal": formal, "fixed_odds_shadow": fixed, "combination_shadow": shadow,
              "non_settleable_early_shadow_labels": [source[0]["shadow_schemes"], source[1]["shadow_schemes"]],
              "source_results": "data/manual/sporttery_results_2026-09-12_sales_window.csv",
              "source_predictions": [f"artifacts/data/sporttery_final_analysis_{DAY}_{name}.json" for name in PICKS],
              "supabase_sync": "not_authorized"}
    output = DATA / f"sporttery_full_review_{DAY}_1300_detailed.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [f"# {DAY}销售日30场详细复盘", "", "官方周六001–030均取得完场及半场赛果；下列所有方案均为本地模拟/影子研究，未向Supabase同步。", "",
             "## 逐场赛果与冻结预测", "",
             "|编号|比赛|半场/全场|SPF首选/防守→实际|让球首选/防守→实际|总进球双选→实际|比分候选→实际|半全场候选→实际|",
             "|---|---|---|---|---|---|---|---|"]
    for item in per_match:
        actual = item["actual"]
        def mark(choices: list[str], winning: str) -> str:
            return f"{'/'.join(choices) or '未开'}→{winning}（{'中' if winning in choices else '未中' if choices else '不计'}）"
        spf = mark([item["primary"], item["defense"]], actual["spf"]) if item["spf_open"] else "未开→不计"
        lines.append(f"|{item['number']}|{item['home']}—{item['away']}|{item['half_time']} / {item['full_time']}|"
                     f"{spf}|{mark([item['rq_primary'], item['rq_defense']], actual['rq'])}|"
                     f"{mark(item['goals'], actual['goals'])}|{mark(item['scores'], actual['score'])}|"
                     f"{mark(item['half_full'], actual['half_full'])}|")
    lines += ["", "## 逐场失误归因", ""]
    for item in per_match:
        actual = item["actual"]
        reasons = []
        if not item["spf_open"]:
            reasons.append("SPF赛前未开，不把结构推断计入胜负命中率")
        elif item["primary"] != actual["spf"]:
            reasons.append("胜负首选未中" + ("，防守方向覆盖" if item["defense"] == actual["spf"] else "，防守方向也未覆盖"))
        if item["rq_primary"] != actual["rq"]:
            reasons.append("让球首选未中" + ("，次选覆盖" if item["rq_defense"] == actual["rq"] else "，次选亦失"))
        if actual["goals"] not in item["goals"]:
            reasons.append(f"实际{actual['goals']}球超出冻结进球候选{'/'.join(item['goals'])}")
        if actual["score"] not in item["scores"]:
            reasons.append("比分候选未覆盖实际比分")
        if item["half_full"] and actual["half_full"] not in item["half_full"]:
            reasons.append("半全场节奏判断未覆盖")
        if item["number"] == "022":
            reasons.append("赛前伤停仅有可用性警报、没有首发，不能把0:0事后归因于确定缺阵")
        lines.append(f"- {item['number']} {item['home']}—{item['away']} {item['full_time']}：{'；'.join(reasons) if reasons else '各项冻结候选覆盖，但不代表模型概率已校准'}。")
    lines += ["", "## 命中统计", ""]
    for key, title in (("spf_primary", "SPF首选"), ("spf_covered", "SPF首选+防守"),
                       ("rq_primary", "让球首选"), ("rq_covered", "让球首选+防守"),
                       ("goals_covered", "总进球双选"), ("score_covered", "比分候选"),
                       ("half_full_covered", "半全场候选")):
        total_key = "spf_total" if key.startswith("spf") else "rq_total" if key.startswith("rq") else key.split("_covered")[0] + "_total"
        lines.append(f"- {title}：{metrics[key + '_hits']}/{metrics[total_key]}。")
    lines += ["", "## 正式模拟方案与固定赔率影子", "", "|类别|方案|选择|结果|投入|返奖|净收益|ROI|逐腿核验|",
              "|---|---|---|---|---:|---:|---:|---:|---|"]
    for category, collection in (("正式", formal), ("固定赔率影子", fixed)):
        for row in collection:
            lines.append(f"|{category}|{row['plan_id']}|{row['selections']}|{row['result']}|{row['stake']}|"
                         f"{row['payout']}|{row['net_profit']}|{float(row['roi']):.0%}|{row['review_note']}|")
    lines += ["", "## 18:30冻结组合影子：逐子注结算", "",
              "复式按每注2元拆分；只计真实命中的子注，赔率均来自冻结选择或同期体彩官方快照。", "",
              "|方案|子注|命中子注|投入|返奖|净收益|ROI|", "|---|---:|---:|---:|---:|---:|---:|"]
    for item in shadow:
        lines.append(f"|{item['name']}|{item['ticket_count']}|{item['hit_tickets']}|{item['stake']:.2f}|"
                     f"{item['payout']:.2f}|{item['net']:.2f}|{item['roi']:.0%}|")
        for index, ticket in enumerate(item["tickets"], 1):
            desc = " × ".join(f"{leg['number']}{leg['pick']}@{leg['odds']:.2f}（实际{leg['actual']}）" for leg in ticket["legs"])
            lines.append(f"- {item['name']} 子注{index}：{desc}；{'命中' if ticket['hit'] else '未中'}；投入{ticket['stake']:.2f}，返奖{ticket['payout']:.2f}。")
    lines += ["", "## 错误归因与边界", "",
              "- SPF方向与让球穿盘必须分开评估；凡首选未中而防守命中的场次，不能计作首选命中。",
              "- 总进球、比分、半全场只按冻结候选逐项计数；030赛前SPF与半全场未开，对应项不计命中率。",
              "- 14:00和16:30报告仅列影子方案名称、未冻结具体投注腿与金额，因此不能事后编造返奖和ROI；仅3组固定赔率影子及18:30的8组明确组合可核算。",
              "- The Odds赛前HTTP 401及未映射的伤停情报不作为预测或赛后归因证据。",
              "- 本次只结算既有记录，没有新增正式方案；2026-09-12尚无Supabase同步授权。", ""]
    markdown = ROOT / f"artifacts/reviews/sporttery_full_review_{DAY}_1300_detailed.md"
    markdown.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"matches": 30, "metrics": dict(metrics), "formal": len(formal), "fixed": len(fixed),
                      "shadow": len(shadow), "report": str(markdown)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
