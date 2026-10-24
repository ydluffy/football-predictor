from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-27"
NOW = "2026-09-28T13:07:01+08:00"


def csv_rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def metric(rows):
    stake = sum(float(row.get("stake") or 0) for row in rows)
    payout = sum(float(row.get("payout") or 0) for row in rows)
    return {
        "plans": len(rows),
        "hits": sum(row.get("result") == "命中" for row in rows),
        "stake": round(stake, 2),
        "payout": round(payout, 2),
        "net": round(payout - stake, 2),
        "roi": None if not stake else round((payout - stake) / stake, 6),
    }


def main():
    baseline_path = ROOT / "artifacts/data/sporttery_early_baseline_2026-09-27_1506_001-009.json"
    final_path = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-27_1609_001-003.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    final = json.loads(final_path.read_text(encoding="utf-8"))

    result_rows = csv_rows(ROOT / "data/manual/sporttery_results_2026-09-27_sales_window.csv")
    results = {}
    for row in result_rows:
        match = re.search(r"(\d+)$", row.get("match_number", ""))
        if match and row.get("match_number", "").startswith("周日") and 1 <= int(match.group(1)) <= 9:
            results[match.group(1).zfill(3)] = row

    baseline_predictions = {row["number"]: row for row in baseline["predictions"]}
    final_predictions = {row["number"]: row for row in final["matches"]}
    per_match = []
    spf_hits = rq_hits = 0
    for number in [f"{i:03d}" for i in range(1, 10)]:
        prediction = final_predictions.get(number) or baseline_predictions[number]
        source = "终版" if number in final_predictions else "15:00基线（终版错过、未回填）"
        result = results[number]
        primary = (prediction.get("primary") or prediction.get("spf_primary") or {})["selection"]
        rq_primary = (prediction.get("rq_primary") or prediction.get("rqspf_primary") or {})["selection"]
        primary_result = {"主胜": "胜", "平": "平", "客胜": "负"}[primary]
        primary_hit = primary_result == result["spf_result"]
        rq_hit = rq_primary == result["rqspf_result"]
        spf_hits += int(primary_hit)
        rq_hits += int(rq_hit)
        per_match.append({
            "match_number": number,
            "match": f'{prediction["home"]} vs {prediction["away"]}',
            "source": source,
            "score": result["full_time_score"],
            "handicap": result["handicap"],
            "spf_result": result["spf_result"],
            "rqspf_result": result["rqspf_result"],
            "primary": primary,
            "primary_hit": primary_hit,
            "rq_primary": rq_primary,
            "rq_primary_hit": rq_hit,
        })

    formal = [row for row in csv_rows(ROOT / "data/manual/betting_plan_ledger.csv") if row.get("date") == DAY]
    fixed = [row for row in csv_rows(ROOT / "data/manual/fixed_odds_shadow_ledger.csv") if row.get("date") == DAY]
    formal_sum = metric(formal)
    fixed_sum = metric(fixed)

    displayed = {
        "plans": 7,
        "hits": 3,
        "stake": 116.0,
        "payout": 265.19,
        "net": 149.19,
        "roi": 1.286121,
        "details": [
            "SAFE命中：002客胜+003主胜，投入50.00，返奖181.30",
            "VALUE命中：002客胜+003主胜，投入20.00，返奖72.52",
            "HEDGE命中1注：003主胜+001平，投入8.00，返奖11.37",
            "HANDICAP、GOALS、SCORE、HALF_FULL均未中",
        ],
    }
    contrarian = {
        "plans": 1,
        "hits": 0,
        "stake": 2.0,
        "payout": 0.0,
        "net": -2.0,
        "roi": -1.0,
        "detail": "003格拉夫(-1)让负@1.64未中，实际让平",
    }

    audit = {
        "schema_version": 1,
        "sales_day": DAY,
        "status": "completed",
        "completed_at": NOW,
        "official_result_coverage": "9/9",
        "analytical_prediction_coverage": "9/9",
        "final_prediction_coverage": "3/9",
        "missed_final_match_numbers": ["004", "005", "006", "007", "008", "009"],
        "post_lock_backfill": False,
        "spf_primary": {"hits": spf_hits, "total": 9, "accuracy": round(spf_hits / 9, 6)},
        "rq_primary": {"hits": rq_hits, "total": 9, "accuracy": round(rq_hits / 9, 6)},
        "formal": formal_sum,
        "fixed_odds_shadow": fixed_sum,
        "displayed_shadow_excluding_fixed_and_contrarian": displayed,
        "contrarian_shadow": contrarian,
        "per_match": per_match,
        "sources": [
            str(baseline_path.relative_to(ROOT)).replace("\\", "/"),
            str(final_path.relative_to(ROOT)).replace("\\", "/"),
            "data/manual/sporttery_results_2026-09-27_sales_window.csv",
            "artifacts/data/missed_final_audit_2026-09-27_004-009.json",
        ],
        "supabase_sync": "not_authorized_for_2026-09-27",
    }
    audit_path = ROOT / "artifacts/data/sporttery_full_review_2026-09-27_1300_detailed.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 2026-09-27 体彩全期逐场复盘", "",
        f"完成时间：{NOW}。官方赛果9/9；001–003有赛前终版，004–009仅有15:00赔率基线，因22:45硬锁后才唤醒而未生成终版，本复盘不做赛后回填。", "",
        "## 逐场结果与赛前主方向", "",
        "|编号|比赛|预测来源|比分|让球|SPF结果/主方向|让球结果/主方向|", "|---|---|---|---:|---:|---|---|",
    ]
    for item in per_match:
        spf = f'{item["spf_result"]} / {item["primary"]}（{"中" if item["primary_hit"] else "未中"}）'
        rq = f'{item["rqspf_result"]} / {item["rq_primary"]}（{"中" if item["rq_primary_hit"] else "未中"}）'
        lines.append(f'|{item["match_number"]}|{item["match"]}|{item["source"]}|{item["score"]}|{item["handicap"]}|{spf}|{rq}|')
    lines += [
        "", "## 正式、固定赔率影子和其他观察（严格分开）", "",
        "- 正式方案：0组，投入0.00元，返奖0.00元，净收益0.00元，ROI不适用。001–003生产策略实际执行但无合格行；004–009未在硬锁前完成终版。",
        f'- 固定赔率影子：{fixed_sum["plans"]}组，命中{fixed_sum["hits"]}组，虚拟投入{fixed_sum["stake"]:.2f}元，返奖{fixed_sum["payout"]:.2f}元，净收益{fixed_sum["net"]:+.2f}元，ROI {fixed_sum["roi"]:.2%}。001平局断腿。',
        f'- 邪修影子：1组，命中0组，虚拟投入2.00元，返奖0.00元，净收益-2.00元，ROI -100.00%；{contrarian["detail"]}。',
        f'- 其余展示观察：7组，命中3组，虚拟投入116.00元，返奖265.19元，净收益+149.19元，ROI {displayed["roi"]:.2%}。',
        "  - " + "；".join(displayed["details"]),
        "", "## 结论", "",
        f"- 以001–003终版、004–009基线合并评估，SPF主方向命中{spf_hits}/9，让球主方向命中{rq_hits}/9。",
        "- 001–003的顺势二串一（002客胜+003主胜）命中，但不满足生产策略门槛，因此只计影子观察，不追认正式方案。",
        "- 004–009缺失终版属于调度到达过晚，复盘只评估既有15:00基线，绝不事后生成赛前方案。",
        "- 未获本销售日Supabase同步授权，本次只更新本地赛果、台账、复盘报告与控制器状态。", "",
        f"结构化审计：`{str(audit_path.relative_to(ROOT)).replace(chr(92), '/')}`", "",
    ]
    report_path = ROOT / "artifacts/reviews/sporttery_full_review_2026-09-27_1300_detailed.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_review_20260927",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-27销售日13:00逐场复盘",
        "last_completed_at": NOW,
        "last_stage_status": "completed_review_9_of_9_no_formal_plan",
        "last_stage_artifact": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "last_reviewed_sales_day": DAY,
        "last_review_artifact": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "next_required_stage": "2026-09-28 16:55终版分析001-002",
        "next_required_at": "2026-09-28T16:55:00+08:00",
        "next_dynamic_task_key": "2026-09-28|18:25-19:00|终版分析",
        "next_dynamic_task_at": "2026-09-28T16:55:00+08:00",
    })
    state.pop("pending_review_settlement", None)
    state["review_20260927"] = {
        "status": "completed",
        "completed_at": NOW,
        "official_result_coverage": "9/9",
        "analytical_prediction_coverage": "9/9",
        "final_prediction_coverage": "3/9",
        "missed_final_match_numbers": ["004", "005", "006", "007", "008", "009"],
        "formal": formal_sum,
        "fixed_shadow": fixed_sum,
        "contrarian_shadow": contrarian,
        "displayed_shadow_excluding_fixed_and_contrarian": displayed,
        "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "audit": str(audit_path.relative_to(ROOT)).replace("\\", "/"),
        "supabase_sync": "not_authorized_for_2026-09-27",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"official": "9/9", "spf": f"{spf_hits}/9", "rqspf": f"{rq_hits}/9", "formal": formal_sum, "fixed": fixed_sum, "displayed": displayed}, ensure_ascii=True))


if __name__ == "__main__":
    main()
