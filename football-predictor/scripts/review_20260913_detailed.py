"""Review the frozen 2026-09-13 manual analysis against official 90-minute scores."""
from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-13"
ANALYSIS = ROOT / "artifacts/data/sporttery_manual_evening_analysis_2026-09-13.json"
RESULTS = ROOT / "data/external/sporttery_results/sporttery_results_2026-09-13_sales_window.csv"
LEDGER = ROOT / "data/manual/betting_plan_ledger.csv"
REPORT = ROOT / "artifacts/reviews/sporttery_full_review_2026-09-13_1300_detailed.md"
AUDIT = ROOT / "artifacts/data/sporttery_full_review_2026-09-13_1300_detailed.json"


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def spf(score: str) -> str:
    home, away = (int(x) for x in score.split(":"))
    return "主胜" if home > away else "客胜" if home < away else "平"


def actual_for_leg(leg: dict, result: dict[str, str]) -> str:
    play = leg["play"]
    if play == "SPF":
        return spf(result["full_time_score"])
    if play == "RQSPF":
        wanted_handicap = int(leg["handicap"])
        if wanted_handicap != int(result["handicap"]):
            raise ValueError(f"handicap mismatch for {leg['match_number']}")
        return {"让胜": "让胜", "让平": "让平", "让负": "让负"}[result["rqspf_result"]]
    if play == "总进球":
        home, away = (int(x) for x in result["full_time_score"].split(":"))
        return "7+球" if home + away >= 7 else f"{home + away}球"
    raise ValueError(f"unsupported play: {play}")


def main() -> None:
    analysis = json.loads(ANALYSIS.read_text(encoding="utf-8"))
    all_results = csv_rows(RESULTS)
    result_by_number: dict[str, dict[str, str]] = {}
    for row in all_results:
        if not row["match_number"].startswith("周日"):
            continue
        number = row["match_number"][-3:]
        if number in result_by_number:
            raise ValueError(f"duplicate official result: {number}")
        if row["status"] != "已完成" or ":" not in row["full_time_score"]:
            raise ValueError(f"no completed 90-minute score: {number}")
        result_by_number[number] = row
    expected = {f"{number:03d}" for number in range(1, 25)}
    if set(result_by_number) != expected:
        raise ValueError(f"official result coverage mismatch: {sorted(expected - set(result_by_number))}")

    ledger = {row["plan_id"]: row for row in csv_rows(LEDGER) if row["date"] == DAY}
    schemes = []
    for scheme in analysis["research_schemes"]:
        legs = []
        product = 1.0
        for item in scheme["legs"]:
            number = item["match_number"]
            official = result_by_number[number]
            actual = actual_for_leg(item, official)
            odds = float(item["odds_at_snapshot"])
            product *= odds
            legs.append({
                "number": number,
                "play": item["play"],
                "handicap": item["handicap"],
                "pick": item["selection"],
                "odds": odds,
                "score": official["full_time_score"],
                "actual": actual,
                "hit": item["selection"] == actual,
            })
        hit = all(leg["hit"] for leg in legs)
        stake = float(scheme["one_ticket_yuan"])
        payout = round(stake * product, 2) if hit else 0.0
        status = scheme["status"]
        if status == "formal_simulation_ledger":
            entry = ledger.get(scheme["plan_id"])
            if not entry or entry["result"] != ("命中" if hit else "未中"):
                raise ValueError(f"formal ledger disagreement: {scheme['plan_id']}")
            if abs(float(entry["payout"]) - payout) > 0.01:
                raise ValueError(f"formal payout disagreement: {scheme['plan_id']}")
        schemes.append({
            "name": scheme["name"], "status": status, "plan_id": scheme.get("plan_id"),
            "legs": legs, "hit": hit, "stake": stake, "frozen_odds_product": round(product, 4),
            "payout": payout, "net": round(payout - stake, 2),
            "roi": round((payout - stake) / stake, 4),
        })

    formal = [x for x in schemes if x["status"] == "formal_simulation_ledger"]
    research = [x for x in schemes if x["status"] != "formal_simulation_ledger"]
    lines = [
        "# 2026-09-13 销售日逐场复盘",
        "",
        f"- 赛前方案冻结：{analysis['frozen_at']}；体彩赔率快照：{analysis['official_captured_at']}。",
        "- 依据体彩官方接口已完成比赛的90分钟比分结算；销售日凌晨赛事在9月14日结束。非实际出票，所有金额均为模拟或研究虚拟金额。",
        "- 001—009无该日晚间冻结预测，不计算预测命中率；010—024有赛前市场预测，外盘未核验，不作外盘结论。",
        "",
        "## 官方赛果及逐场预测核验",
        "",
        "| 场次 | 比赛 | 90分钟 | SPF / 让球 | 赛前主向核验 |",
        "|---|---|---|---|---|",
    ]
    predictions = {p["number"]: p for p in analysis["predictions"]}
    primary_total = primary_hits = 0
    rq_total = rq_hits = 0
    for number in sorted(result_by_number):
        row = result_by_number[number]
        pred = predictions.get(number)
        actual_spf = spf(row["full_time_score"])
        actual_rq = row["rqspf_result"]
        actual_label = f"{actual_spf} / {row['handicap']} {actual_rq}"
        note = "未冻结预测"
        if pred:
            parts = []
            if pred["primary"]:
                primary_total += 1
                pick = {"H": "主胜", "D": "平", "A": "客胜"}[pred["primary"][0][0]]
                hit = pick == actual_spf
                primary_hits += hit
                parts.append(f"SPF {pick}{'中' if hit else '失'}")
            else:
                parts.append("SPF未开盘")
            if pred["rq_primary"]:
                rq_total += 1
                pick = {"H": "让胜", "D": "让平", "A": "让负"}[pred["rq_primary"][0][0]]
                hit = pick == actual_rq
                rq_hits += hit
                parts.append(f"让球 {pick}{'中' if hit else '失'}")
            note = "；".join(parts)
        lines.append(f"| {number} | {row['home_team']} vs {row['away_team']} | {row['full_time_score']} | {actual_label} | {note} |")
    lines.extend([
        "", f"普通胜平负首选：{primary_hits}/{primary_total}；让球首选：{rq_hits}/{rq_total}。",
        "", "## 方案逐腿复盘", "",
    ])
    for item in schemes:
        category = "正式模拟台账" if item in formal else "赛前冻结研究影子（未入台账）"
        lines.extend([
            f"### {item['name']}｜{category}", "",
            f"- 2串1；虚拟本金 {item['stake']:.2f} 元；冻结赔率乘积 {item['frozen_odds_product']:.4f}；"
            f"{'命中' if item['hit'] else '未中'}；返奖 {item['payout']:.2f} 元；净额 {item['net']:+.2f} 元；ROI {item['roi']:.0%}。",
        ])
        for leg in item["legs"]:
            mark = "中" if leg["hit"] else "失（断票腿）"
            lines.append(
                f"- {leg['number']} {leg['play']}{'('+str(leg['handicap'])+')' if leg['handicap'] else ''} "
                f"选{leg['pick']}@{leg['odds']:.2f}；90分钟 {leg['score']}，实际{leg['actual']}：{mark}。"
            )
        lines.append("")
    for label, group in (("正式模拟", formal), ("研究影子", research)):
        stake = sum(x["stake"] for x in group)
        payout = sum(x["payout"] for x in group)
        lines.append(f"- {label}：{sum(x['hit'] for x in group)}/{len(group)}组命中；投入 {stake:.2f} 元，返奖 {payout:.2f} 元，净额 {payout-stake:+.2f} 元，ROI {(payout-stake)/stake:.0%}。")
    lines.extend([
        "", "## 归因与边界", "",
        "- 稳健组两场热门客胜均落空；均衡组曼城客胜命中，但赫塔费主胜被平局断票。",
        "- 研究影子四组独立于正式模拟台账。固定赔率影子台账与v2影子台账在该销售日无新票，不把上述四组冒充已入账记录。",
        "- 赔率为赛前快照，不代表真实出票SP；本次无命中返奖，因此不影响损益结果。不可用赛后信息改写赛前判断。",
        "- 下轮改进：把低赔热门与让球分歧、平局风险单列为弃投信号；外盘不足时继续降级，不提高预算。",
    ])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    audit = {
        "sales_day": DAY, "official_result_count": len(result_by_number),
        "prediction_count": len(predictions),
        "spf_primary": {"hits": primary_hits, "total": primary_total},
        "rq_primary": {"hits": rq_hits, "total": rq_total},
        "formal": formal, "research_shadow": research,
        "report": str(REPORT), "official_results_csv": str(RESULTS),
        "production_ledger_write_performed": False,
    }
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: audit[k] for k in ("official_result_count", "prediction_count", "spf_primary", "rq_primary", "report")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
