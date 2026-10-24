from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-28"
NOW = "2026-09-29T13:06:55+08:00"
AUDIT_PATH = ROOT / "artifacts/data/sporttery_full_review_2026-09-28_1300_detailed.json"
REPORT_PATH = ROOT / "artifacts/reviews/sporttery_full_review_2026-09-28_1300_detailed.md"


def rows(path: str) -> list[dict[str, str]]:
    with (ROOT / path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def metric(stake: float, payout: float, plans: int, hits: int) -> dict:
    return {
        "plans": plans,
        "hits": hits,
        "stake": round(stake, 2),
        "payout": round(payout, 2),
        "net": round(payout - stake, 2),
        "roi": None if not stake else round((payout - stake) / stake, 6),
    }


def main() -> None:
    audits = [
        json.loads((ROOT / "artifacts/data/sporttery_final_analysis_2026-09-28_1706_001-002.json").read_text(encoding="utf-8")),
        json.loads((ROOT / "artifacts/data/sporttery_final_analysis_2026-09-28_2106_003-008.json").read_text(encoding="utf-8")),
    ]
    predictions = {m["number"]: m for audit in audits for m in audit["matches"]}
    result_rows = rows("data/manual/sporttery_results_2026-09-28_sales_window.csv")
    expected_teams = {n: (p["home"], p["away"]) for n, p in predictions.items()}
    results: dict[str, dict[str, str]] = {}
    for row in result_rows:
        match = re.search(r"(\d{3})$", row["match_number"])
        if not match:
            continue
        number = match.group(1)
        teams = expected_teams.get(number)
        if teams and row["home_team"] == teams[0] and row["away_team"] == teams[1]:
            results[number] = row
    if set(results) != set(expected_teams):
        raise ValueError(f"official result coverage mismatch: {sorted(results)}")

    per_match = []
    spf_hits = rq_hits = 0
    for number in sorted(predictions):
        pred = predictions[number]
        result = results[number]
        primary_result = {"主胜": "胜", "平": "平", "客胜": "负"}[pred["primary"]["selection"]]
        spf_hit = primary_result == result["spf_result"]
        rq_hit = pred["rq_primary"]["selection"] == result["rqspf_result"]
        spf_hits += int(spf_hit)
        rq_hits += int(rq_hit)
        per_match.append({
            "match_number": number,
            "match": f'{pred["home"]} vs {pred["away"]}',
            "score": result["full_time_score"],
            "handicap": result["handicap"],
            "spf_result": result["spf_result"],
            "primary": pred["primary"]["selection"],
            "primary_hit": spf_hit,
            "rqspf_result": result["rqspf_result"],
            "rq_primary": pred["rq_primary"]["selection"],
            "rq_primary_hit": rq_hit,
            "formal_stake": 0.0,
            "formal_payout": 0.0,
            "formal_net": 0.0,
            "formal_roi": None,
        })

    formal_rows = [r for r in rows("data/manual/betting_plan_ledger.csv") if r.get("date") == DAY]
    if formal_rows:
        raise ValueError("unexpected formal ledger rows for 2026-09-28")
    fixed_rows = [r for r in rows("data/manual/fixed_odds_shadow_ledger.csv") if r.get("date") == DAY]
    fixed_stake = sum(float(r.get("stake") or 0) for r in fixed_rows)
    fixed_payout = sum(float(r.get("payout") or 0) for r in fixed_rows)
    fixed = metric(fixed_stake, fixed_payout, len(fixed_rows), sum(r.get("result") == "命中" for r in fixed_rows))
    formal = metric(0, 0, 0, 0)
    contrarian = metric(4.0, 5.80, 2, 2)
    contrarian["details"] = [
        "002韩国(-1)让负@1.47命中：投入2.00，返奖2.94，净收益+0.94，ROI +47.00%",
        "008北爱尔兰(+1)让胜@1.43命中：投入2.00，返奖2.86，净收益+0.86，ROI +43.00%",
    ]
    displayed = metric(222.0, 244.94, 14, 4)
    displayed["details"] = [
        "17:06防冷复式命中1注（002客胜+001主胜）：总投入8.00，返奖6.12，净收益-1.88，ROI -23.50%",
        "21:06顺势观察命中（005客胜+007主胜）：投入50.00，返奖143.62，净收益+93.62，ROI +187.24%",
        "21:06市场组合观察命中同一组合：投入20.00，返奖57.45，净收益+37.45，ROI +187.25%",
        "21:06让球结构命中（003让负+008让胜）：投入20.00，返奖37.75，净收益+17.75，ROI +88.75%",
        "其余10组观察均未中；固定赔率候选和邪修另表统计，不计入本项",
    ]

    audit = {
        "schema_version": 1,
        "sales_day": DAY,
        "status": "completed",
        "completed_at": NOW,
        "official_result_coverage": "8/8",
        "final_prediction_coverage": "8/8",
        "post_lock_backfill": False,
        "spf_primary": {"hits": spf_hits, "total": 8, "accuracy": round(spf_hits / 8, 6)},
        "rq_primary": {"hits": rq_hits, "total": 8, "accuracy": round(rq_hits / 8, 6)},
        "formal": formal,
        "fixed_odds_shadow": fixed,
        "contrarian_shadow": contrarian,
        "displayed_shadow_excluding_fixed_and_contrarian": displayed,
        "per_match": per_match,
        "sources": [
            "artifacts/data/sporttery_final_analysis_2026-09-28_1706_001-002.json",
            "artifacts/data/sporttery_final_analysis_2026-09-28_2106_003-008.json",
            "data/manual/sporttery_results_2026-09-28_sales_window.csv",
        ],
        "production_ledger_sha256": hashlib.sha256((ROOT / "data/manual/betting_plan_ledger.csv").read_bytes()).hexdigest(),
        "supabase_sync": "not_authorized_for_2026-09-28",
    }
    AUDIT_PATH.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 2026-09-28 体彩全期逐场复盘", "",
        f"完成时间：{NOW}。官方90分钟赛果8/8，赛前终版覆盖8/8；不做赛后回填。", "",
        "## 逐场结果与赛前主方向", "",
        "|编号|比赛|比分|让球|SPF结果/主方向|让球结果/主方向|正式投入|返奖|净收益|ROI|",
        "|---|---|---:|---:|---|---|---:|---:|---:|---:|",
    ]
    for item in per_match:
        spf = f'{item["spf_result"]} / {item["primary"]}（{"中" if item["primary_hit"] else "未中"}）'
        rq = f'{item["rqspf_result"]} / {item["rq_primary"]}（{"中" if item["rq_primary_hit"] else "未中"}）'
        lines.append(f'|{item["match_number"]}|{item["match"]}|{item["score"]}|{item["handicap"]}|{spf}|{rq}|0.00|0.00|0.00|不适用|')
    lines += [
        "", "## 正式、固定赔率影子和其他观察（严格分开）", "",
        "- 正式方案：0组；逐场正式投入均为0元，总投入0.00元、返奖0.00元、净收益0.00元，ROI不适用。两个终版批次均实际执行生产策略，但合格腿不足。",
        f'- 固定赔率影子：{fixed["plans"]}组，命中{fixed["hits"]}组，虚拟投入{fixed["stake"]:.2f}元、返奖{fixed["payout"]:.2f}元、净收益{fixed["net"]:+.2f}元、ROI {fixed["roi"]:.2%}；004意大利客胜命中、006罗马尼亚主胜未中、007瑞典主胜命中。',
        f'- 邪修影子：{contrarian["plans"]}组，命中{contrarian["hits"]}组，虚拟投入{contrarian["stake"]:.2f}元、返奖{contrarian["payout"]:.2f}元、净收益{contrarian["net"]:+.2f}元、ROI {contrarian["roi"]:.2%}。',
        "  - " + "；".join(contrarian["details"]),
        f'- 其余展示观察：14组，命中4组（含1个复式中的1注），虚拟投入{displayed["stake"]:.2f}元、返奖{displayed["payout"]:.2f}元、净收益{displayed["net"]:+.2f}元、ROI {displayed["roi"]:.2%}。',
        "  - " + "；".join(displayed["details"]),
        "", "## 结论", "",
        f"- SPF赛前主方向命中{spf_hits}/8（{spf_hits/8:.2%}），让球主方向命中{rq_hits}/8（{rq_hits/8:.2%}）。",
        "- 昨日没有任何正式投入，影子盈利不得追认为真实收益或事后升级为正式方案。",
        "- 捷报数据只用于赛前外盘影子对照，没有成为生产模型特征；复盘仍以体彩官方90分钟赛果结算。",
        "- 未获该销售日Supabase同步授权，本次只更新本地赛果、台账、复盘报告和控制器状态。", "",
        f"结构化审计：`{AUDIT_PATH.relative_to(ROOT).as_posix()}`", "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_review_20260928",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-28销售日13:00逐场复盘",
        "last_completed_at": NOW,
        "last_stage_status": "completed_review_8_of_8_no_formal_plan",
        "last_stage_artifact": REPORT_PATH.relative_to(ROOT).as_posix(),
        "last_reviewed_sales_day": DAY,
        "last_review_artifact": REPORT_PATH.relative_to(ROOT).as_posix(),
        "next_required_stage": "2026-09-29 16:30终版分析002-007",
        "next_required_at": "2026-09-29T16:30:00+08:00",
        "next_dynamic_task_key": "2026-09-29|18:00-18:30|终版分析",
        "next_dynamic_task_at": "2026-09-29T16:30:00+08:00",
        "pending_reschedule": True,
        "pending_reschedule_reason": "fixed heartbeat remains active; next registry task is 002-007 at 16:30",
    })
    state["review_20260928"] = {
        "status": "completed",
        "completed_at": NOW,
        "official_result_coverage": "8/8",
        "final_prediction_coverage": "8/8",
        "formal": formal,
        "fixed_shadow": fixed,
        "contrarian_shadow": contrarian,
        "displayed_shadow_excluding_fixed_and_contrarian": displayed,
        "report": REPORT_PATH.relative_to(ROOT).as_posix(),
        "audit": AUDIT_PATH.relative_to(ROOT).as_posix(),
        "supabase_sync": "not_authorized_for_2026-09-28",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"official": "8/8", "spf": f"{spf_hits}/8", "rqspf": f"{rq_hits}/8", "formal": formal, "fixed": fixed, "contrarian": contrarian, "displayed": displayed}, ensure_ascii=True))


if __name__ == "__main__":
    main()
