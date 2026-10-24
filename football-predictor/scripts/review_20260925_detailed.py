from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-25"
NOW = "2026-09-26T13:20:00+08:00"
SOURCES = [
    ROOT / "artifacts/data/sporttery_final_analysis_2026-09-25_1223_001-002.json",
    ROOT / "artifacts/data/sporttery_final_analysis_2026-09-25_1705_003-005.json",
    ROOT / "artifacts/data/sporttery_final_analysis_2026-09-25_2122_006-013.json",
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
    return {"plans": len(items), "hits": sum(x.get("result") == "命中" for x in items), "stake": stake,
            "payout": payout, "net": payout - stake, "roi": None if not stake else (payout - stake) / stake}


def main():
    result_rows = [r for r in rows(ROOT / "data/manual/sporttery_results_2026-09-25_sales_window.csv")
                   if r["match_number"].startswith("周五") and 1 <= int(re.search(r"(\d+)$", r["match_number"]).group(1)) <= 13]
    results = {re.search(r"(\d+)$", r["match_number"]).group(1).zfill(3): r for r in result_rows}
    predictions = {}
    for path in SOURCES:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for match in payload["matches"]:
            predictions[match["number"]] = match
    per = []
    spf_hits = rq_hits = spf_total = rq_total = 0
    for number in sorted(results):
        r = results[number]; p = predictions.get(number, {})
        primary = (p.get("primary") or {}).get("selection")
        rq_primary = (p.get("rq_primary") or {}).get("selection")
        if primary:
            spf_total += 1; spf_hits += primary == r["spf_result"]
        if rq_primary:
            rq_total += 1; rq_hits += rq_primary == r["rqspf_result"]
        per.append({
            "match_number": number, "match": f"{r['home_team']} vs {r['away_team']}",
            "score": r["full_time_score"], "handicap": r["handicap"], "spf_result": r["spf_result"],
            "rqspf_result": r["rqspf_result"], "primary": primary, "primary_hit": primary == r["spf_result"] if primary else None,
            "rq_primary": rq_primary, "rq_primary_hit": rq_primary == r["rqspf_result"] if rq_primary else None,
            "goals": sum(map(int, r["full_time_score"].split(":"))),
        })
    formal = [r for r in rows(ROOT / "data/manual/betting_plan_ledger.csv") if r.get("date") == DAY]
    fixed = [r for r in rows(ROOT / "data/manual/fixed_odds_shadow_ledger.csv") if r.get("date") == DAY]
    formal_sum, fixed_sum = summary(formal), summary(fixed)
    contra = {"plans": 3, "hits": 1, "stake": 6.0, "payout": 3.54, "net": -2.46, "roi": -0.41,
              "detail": ["001(-1)让负@2.29：未中（实际让胜）", "005(-3)让负@2.03：未中（实际让平）", "013(+1)让胜@1.77：命中"]}
    audit = {
        "sales_day": DAY, "status": "completed", "completed_at": NOW,
        "official_result_coverage": f"{len(results)}/13", "prediction_coverage": f"{len(predictions)}/13",
        "spf_primary": {"hits": spf_hits, "total": spf_total, "accuracy": spf_hits / spf_total if spf_total else None},
        "rq_primary": {"hits": rq_hits, "total": rq_total, "accuracy": rq_hits / rq_total if rq_total else None},
        "formal": formal_sum, "fixed_odds_shadow": fixed_sum, "contrarian_shadow": contra,
        "per_match": per, "sources": [str(p.relative_to(ROOT)).replace("\\", "/") for p in SOURCES],
        "supabase_sync": "not_authorized_for_2026-09-25",
    }
    audit_path = ROOT / "artifacts/data/sporttery_full_review_2026-09-25_1300_detailed.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# 2026-09-25 体彩全期逐场复盘", "", f"完成时间：{NOW}。官方赛果覆盖{len(results)}/13，终版预测覆盖{len(predictions)}/13。", "",
        "## 逐场结果与主方向", "", "|编号|比赛|比分|让球|SPF结果/主预测|让球结果/主预测|", "|---|---|---:|---:|---|---|",
    ]
    for x in per:
        ps = f"{x['spf_result']} / {x['primary'] or '未开'}（{'中' if x['primary_hit'] else '未中' if x['primary_hit'] is False else '不评'}）"
        rs = f"{x['rqspf_result']} / {x['rq_primary'] or '无'}（{'中' if x['rq_primary_hit'] else '未中' if x['rq_primary_hit'] is False else '不评'}）"
        lines.append(f"|{x['match_number']}|{x['match']}|{x['score']}|{x['handicap']}|{ps}|{rs}|")
    lines += [
        "", "## 正式与影子收益（严格分开）", "",
        f"- 正式模拟：{formal_sum['plans']}组，命中{formal_sum['hits']}组，投入{formal_sum['stake']:.2f}元，返奖{formal_sum['payout']:.2f}元，净收益{formal_sum['net']:+.2f}元，ROI {formal_sum['roi']:.2%}。",
        f"- 固定赔率影子：{fixed_sum['plans']}组，命中{fixed_sum['hits']}组，虚拟投入{fixed_sum['stake']:.2f}元，返奖{fixed_sum['payout']:.2f}元，净收益{fixed_sum['net']:+.2f}元，ROI {fixed_sum['roi']:.2%}。",
        f"- 邪修影子：{contra['plans']}组，命中{contra['hits']}组，虚拟投入{contra['stake']:.2f}元，返奖{contra['payout']:.2f}元，净收益{contra['net']:+.2f}元，ROI {contra['roi']:.2%}。",
        "  - " + "；".join(contra["detail"]),
        "", "## 结论", "",
        f"- SPF主方向命中{spf_hits}/{spf_total}；让球主方向命中{rq_hits}/{rq_total}。",
        "- 两组正式稳健均未中：003巴西未能取胜，006格鲁吉亚主胜落空；说明低赔串关仍有单腿断裂风险，不能把热门方向当保本。",
        "- 007主胜与012主胜打出，但深盘边界频繁落在让平/让负；胜负与穿盘必须继续分层建模。",
        "- 未获本销售日Supabase同步授权，本次只更新本地报告、台账和控制器状态。", "",
    ]
    report_path = ROOT / "artifacts/reviews/sporttery_full_review_2026-09-25_1300_detailed.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_review_20260925",
        "last_heartbeat_at": NOW, "last_completed_stage": "2026-09-25销售日13:00逐场复盘",
        "last_completed_at": NOW, "last_stage_status": "completed_review_13_of_13_two_formal_lost",
        "last_stage_artifact": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "last_reviewed_sales_day": DAY, "last_review_artifact": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "next_required_stage": "2026-09-26 14:30终版分析002-006",
        "next_required_at": "2026-09-26T14:30:00+08:00",
        "next_dynamic_task_key": "2026-09-26|16:00|终版分析",
        "next_dynamic_task_at": "2026-09-26T14:30:00+08:00",
    })
    state["review_20260925"] = {"status": "completed", "completed_at": NOW, "official_result_coverage": "13/13",
        "prediction_coverage": f"{len(predictions)}/13", "formal": formal_sum, "fixed_shadow": fixed_sum,
        "contrarian_shadow": contra, "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "audit": str(audit_path.relative_to(ROOT)).replace("\\", "/"), "supabase_sync": "not_authorized_for_2026-09-25"}
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "official": len(results), "formal": formal_sum, "fixed": fixed_sum, "contra": contra}, ensure_ascii=False))


if __name__ == "__main__":
    main()
