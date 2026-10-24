from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-26"
NOW = "2026-09-27T13:15:00+08:00"
SOURCES = [
    ROOT / "artifacts/data/sporttery_final_analysis_2026-09-26_1310_001.json",
    ROOT / "artifacts/data/sporttery_final_analysis_2026-09-26_1505_002-006.json",
    ROOT / "artifacts/data/sporttery_final_analysis_2026-09-26_1705_007.json",
    ROOT / "artifacts/data/sporttery_final_analysis_2026-09-26_2006_008-009.json",
    ROOT / "artifacts/data/sporttery_final_analysis_2026-09-26_2206_010-023.json",
]


def rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def amount(row, key):
    try:
        return float(row.get(key) or 0)
    except ValueError:
        return 0.0


def summary(items):
    stake = sum(amount(x, "stake") for x in items)
    payout = sum(amount(x, "payout") for x in items)
    return {
        "plans": len(items), "hits": sum(x.get("result") == "命中" for x in items),
        "stake": stake, "payout": payout, "net": payout - stake,
        "roi": None if not stake else (payout - stake) / stake,
    }


def normalize_spf(selection):
    return {"主胜": "胜", "平": "平", "客胜": "负"}.get(selection, selection)


def main():
    result_rows = []
    for row in rows(ROOT / "data/manual/sporttery_results_2026-09-26_sales_window.csv"):
        match = re.search(r"(\d+)$", row.get("match_number", ""))
        if row.get("match_number", "").startswith("周六") and match and 1 <= int(match.group(1)) <= 23:
            result_rows.append(row)
    results = {re.search(r"(\d+)$", r["match_number"]).group(1).zfill(3): r for r in result_rows}

    predictions = {}
    contrarian = []
    shadow_scheme_count = 0
    for path in SOURCES:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for match in payload["matches"]:
            predictions[match["number"]] = match
        shadow_scheme_count += len(payload.get("shadow_schemes", []))
        candidate = payload.get("contrarian_market_shadow") or {}
        if candidate.get("status") == "candidate":
            contrarian.append(candidate)

    per_match = []
    spf_hits = rq_hits = spf_total = rq_total = 0
    for number in sorted(predictions):
        prediction = predictions[number]
        result = results.get(number)
        primary = (prediction.get("primary") or {}).get("selection")
        rq_primary = (prediction.get("rq_primary") or {}).get("selection")
        settled = bool(result and result.get("full_time_score"))
        primary_hit = None
        rq_primary_hit = None
        if settled and primary:
            spf_total += 1
            primary_hit = normalize_spf(primary) == result["spf_result"]
            spf_hits += int(primary_hit)
        if settled and rq_primary:
            rq_total += 1
            rq_primary_hit = rq_primary == result["rqspf_result"]
            rq_hits += int(rq_primary_hit)
        per_match.append({
            "match_number": number,
            "match": f'{prediction["home"]} vs {prediction["away"]}',
            "status": "settled" if settled else "pending_official_result",
            "score": result["full_time_score"] if settled else "待官方赛果",
            "handicap": result["handicap"] if settled else prediction.get("handicap"),
            "spf_result": result["spf_result"] if settled else None,
            "rqspf_result": result["rqspf_result"] if settled else None,
            "primary": primary, "primary_hit": primary_hit,
            "rq_primary": rq_primary, "rq_primary_hit": rq_primary_hit,
        })

    formal = [r for r in rows(ROOT / "data/manual/betting_plan_ledger.csv") if r.get("date") == DAY]
    fixed = [r for r in rows(ROOT / "data/manual/fixed_odds_shadow_ledger.csv") if r.get("date") == DAY]
    formal_sum = summary(formal)
    fixed_sum = summary(fixed)

    contra_details = []
    contra_payout = 0.0
    contra_hits = 0
    for candidate in contrarian:
        number = candidate["match_number"]
        result = results.get(number)
        selection = re.search(r"(让胜|让平|让负)@", candidate["selection"])
        picked = selection.group(1) if selection else ""
        hit = bool(result and result.get("full_time_score") and picked == result["rqspf_result"])
        payout = float(candidate["virtual_stake"]) * float(candidate["odds"]) if hit else 0.0
        contra_hits += int(hit)
        contra_payout += payout
        actual = result["rqspf_result"] if result and result.get("full_time_score") else "待官方赛果"
        contra_details.append(f'{candidate["selection"]}：{"命中" if hit else "未中"}（实际{actual}）')
    contra_stake = sum(float(x["virtual_stake"]) for x in contrarian)
    contra_sum = {
        "plans": len(contrarian), "hits": contra_hits, "stake": contra_stake,
        "payout": round(contra_payout, 2), "net": round(contra_payout - contra_stake, 2),
        "roi": None if not contra_stake else (contra_payout - contra_stake) / contra_stake,
        "detail": contra_details,
    }

    audit = {
        "sales_day": DAY, "status": "completed_with_one_pending_result", "completed_at": NOW,
        "official_result_coverage": "22/23", "pending_match_numbers": ["019"],
        "prediction_coverage": f"{len(predictions)}/23",
        "spf_primary": {"hits": spf_hits, "total": spf_total, "accuracy": spf_hits / spf_total},
        "rq_primary": {"hits": rq_hits, "total": rq_total, "accuracy": rq_hits / rq_total},
        "formal": formal_sum, "fixed_odds_shadow": fixed_sum,
        "contrarian_shadow": contra_sum, "other_shadow_scheme_count": shadow_scheme_count,
        "per_match": per_match,
        "sources": [str(path.relative_to(ROOT)).replace("\\", "/") for path in SOURCES],
        "supabase_sync": "not_authorized_for_2026-09-26",
    }
    audit_path = ROOT / "artifacts/data/sporttery_full_review_2026-09-26_1300_detailed.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 2026-09-26 体彩全期逐场复盘", "",
        f"完成时间：{NOW}。官方赛果覆盖22/23；019纽约红牛 vs 圣路易城尚无官方90分钟赛果，保持待核验。终版预测覆盖23/23。", "",
        "## 逐场结果与主方向", "",
        "|编号|比赛|比分|让球|SPF结果/主预测|让球结果/主预测|", "|---|---|---:|---:|---|---|",
    ]
    for item in per_match:
        if item["status"] != "settled":
            lines.append(f'|{item["match_number"]}|{item["match"]}|待官方赛果|{item["handicap"]}|待核验 / {item["primary"]}|待核验 / {item["rq_primary"]}|')
            continue
        spf = f'{item["spf_result"]} / {item["primary"]}（{"中" if item["primary_hit"] else "未中"}）'
        rq = f'{item["rqspf_result"]} / {item["rq_primary"]}（{"中" if item["rq_primary_hit"] else "未中"}）'
        lines.append(f'|{item["match_number"]}|{item["match"]}|{item["score"]}|{item["handicap"]}|{spf}|{rq}|')
    lines += [
        "", "## 正式与影子收益（严格分开）", "",
        f'- 正式模拟：{formal_sum["plans"]}组，命中{formal_sum["hits"]}组，投入{formal_sum["stake"]:.2f}元，返奖{formal_sum["payout"]:.2f}元，净收益{formal_sum["net"]:+.2f}元，ROI {formal_sum["roi"]:.2%}。',
        f'- 固定赔率影子：{fixed_sum["plans"]}组，命中{fixed_sum["hits"]}组，虚拟投入{fixed_sum["stake"]:.2f}元，返奖{fixed_sum["payout"]:.2f}元，净收益{fixed_sum["net"]:+.2f}元，ROI {fixed_sum["roi"]:.2%}。',
        f'- 邪修影子：{contra_sum["plans"]}组，命中{contra_sum["hits"]}组，虚拟投入{contra_sum["stake"]:.2f}元，返奖{contra_sum["payout"]:.2f}元，净收益{contra_sum["net"]:+.2f}元，ROI {contra_sum["roi"]:.2%}。',
        "  - " + "；".join(contra_details),
        "", "## 结论", "",
        f"- 已结算22场中，SPF主方向命中{spf_hits}/{spf_total}；让球主方向命中{rq_hits}/{rq_total}。",
        "- 正式稳健方案被011冰岛1:1逼平断腿；正式价值方案由015瑞士客胜与022纳什维尔主胜组成，整票命中。",
        "- 固定赔率影子前批未中，晚间7.9827倍三腿组合命中；影子收益不并入正式结果。",
        "- 019保持待核验，不猜测赛果、不回填预测；后续官方数据出现时再幂等补结算。",
        "- 未获本销售日Supabase同步授权，本次只更新本地报告、台账和控制器状态。", "",
        f"结构化审计：`{str(audit_path.relative_to(ROOT)).replace(chr(92), '/')}`", "",
    ]
    report_path = ROOT / "artifacts/reviews/sporttery_full_review_2026-09-26_1300_detailed.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_review_20260926_one_pending_result",
        "last_heartbeat_at": NOW, "last_completed_stage": "2026-09-26销售日13:00逐场复盘",
        "last_completed_at": NOW, "last_stage_status": "completed_review_22_of_23_one_formal_hit",
        "last_stage_artifact": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "last_reviewed_sales_day": DAY,
        "last_review_artifact": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "next_required_stage": "2026-09-27 15:00全9场赔率基线；16:30终版001-003",
        "next_required_at": "2026-09-27T15:00:00+08:00",
        "next_dynamic_task_key": "2026-09-27|15:00|全9场赔率基线",
        "next_dynamic_task_at": "2026-09-27T15:00:00+08:00",
        "pending_review_settlement": "2026-09-26|019|official_90_minute_result_missing",
    })
    state["review_20260926"] = {
        "status": "completed_with_one_pending_result", "completed_at": NOW,
        "official_result_coverage": "22/23", "pending_match_numbers": ["019"],
        "prediction_coverage": "23/23", "formal": formal_sum, "fixed_shadow": fixed_sum,
        "contrarian_shadow": contra_sum,
        "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "audit": str(audit_path.relative_to(ROOT)).replace("\\", "/"),
        "supabase_sync": "not_authorized_for_2026-09-26",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": audit["status"], "official": "22/23", "pending": ["019"],
        "formal": formal_sum, "fixed": fixed_sum, "contrarian": contra_sum,
        "spf": f"{spf_hits}/{spf_total}", "rqspf": f"{rq_hits}/{rq_total}",
    }, ensure_ascii=True))


if __name__ == "__main__":
    main()
