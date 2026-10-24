from __future__ import annotations

import csv
import hashlib
import json
import re
from decimal import Decimal, ROUND_DOWN
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-29"
NOW = "2026-09-30T13:05:55+08:00"
AUDIT_PATH = ROOT / "artifacts/data/sporttery_full_review_2026-09-29_1300_detailed.json"
REPORT_PATH = ROOT / "artifacts/reviews/sporttery_full_review_2026-09-29_1300_detailed.md"


def rows(path: str) -> list[dict[str, str]]:
    with (ROOT / path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def metric(records: list[dict[str, str]]) -> dict:
    stake = sum(Decimal(row.get("stake") or "0") for row in records)
    payout = sum(Decimal(row.get("payout") or "0") for row in records)
    return {
        "plans": len(records),
        "hits": sum(row.get("result") == "命中" for row in records),
        "stake": float(stake),
        "payout": float(payout),
        "net": float(payout - stake),
        "roi": None if not stake else round(float((payout - stake) / stake), 6),
    }


def main() -> None:
    audit_files = [
        "artifacts/data/sporttery_final_analysis_2026-09-29_1306_001.json",
        "artifacts/data/sporttery_final_analysis_2026-09-29_1605_002-007.json",
        "artifacts/data/sporttery_final_analysis_2026-09-29_2106_008-015.json",
    ]
    audits = [json.loads((ROOT / path).read_text(encoding="utf-8")) for path in audit_files]
    predictions = {match["number"]: match for audit in audits for match in audit["matches"]}
    expected_teams = {number: (match["home"], match["away"]) for number, match in predictions.items()}

    results: dict[str, dict[str, str]] = {}
    for row in rows("data/manual/sporttery_results_2026-09-29_sales_window.csv"):
        match = re.search(r"(\d{3})$", row["match_number"])
        if not match:
            continue
        number = match.group(1)
        teams = expected_teams.get(number)
        if teams and row["home_team"] == teams[0] and row["away_team"] == teams[1]:
            results[number] = row
    if set(results) != set(expected_teams):
        raise ValueError(f"official result coverage mismatch: {sorted(results)}")

    formal_rows = [row for row in rows("data/manual/betting_plan_ledger.csv") if row.get("date") == DAY]
    fixed_rows = [row for row in rows("data/manual/fixed_odds_shadow_ledger.csv") if row.get("date") == DAY]
    if any(row.get("result") not in {"命中", "未中"} for row in formal_rows + fixed_rows):
        raise ValueError("unsettled ledger rows remain")
    formal = metric(formal_rows)
    fixed = metric(fixed_rows)

    # Attribute each two-leg formal ticket equally to its two matches.  Payout cents
    # are split deterministically so the per-match figures reconcile exactly to the ledger.
    attribution = {number: {"stake": Decimal("0"), "payout": Decimal("0"), "plans": []} for number in predictions}
    for plan in formal_rows:
        legs = re.findall(r"(?:^|\+\s*)(\d{3})\s", plan["selections"])
        if len(legs) != 2:
            raise ValueError(f"expected two formal legs: {plan['plan_id']}")
        stake = Decimal(plan["stake"])
        payout = Decimal(plan["payout"])
        stake_parts = [stake / 2, stake / 2]
        first_payout = (payout / 2).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        payout_parts = [first_payout, payout - first_payout]
        for index, number in enumerate(legs):
            attribution[number]["stake"] += stake_parts[index]
            attribution[number]["payout"] += payout_parts[index]
            attribution[number]["plans"].append(plan["plan_id"])

    per_match = []
    spf_hits = rq_hits = 0
    for number in sorted(predictions):
        pred = predictions[number]
        result = results[number]
        primary_result = {"主胜": "胜", "平": "平", "客胜": "负"}[pred["primary"]["selection"]]
        primary_hit = primary_result == result["spf_result"]
        rq_hit = pred["rq_primary"]["selection"] == result["rqspf_result"]
        spf_hits += int(primary_hit)
        rq_hits += int(rq_hit)
        stake = attribution[number]["stake"]
        payout = attribution[number]["payout"]
        net = payout - stake
        per_match.append({
            "match_number": number,
            "match": f'{pred["home"]} vs {pred["away"]}',
            "score": result["full_time_score"],
            "handicap": result["handicap"],
            "spf_result": result["spf_result"],
            "primary": pred["primary"]["selection"],
            "primary_hit": primary_hit,
            "rqspf_result": result["rqspf_result"],
            "rq_primary": pred["rq_primary"]["selection"],
            "rq_primary_hit": rq_hit,
            "formal_plan_ids": attribution[number]["plans"],
            "formal_stake_attributed": float(stake),
            "formal_payout_attributed": float(payout),
            "formal_net_attributed": float(net),
            "formal_roi_attributed": None if not stake else round(float(net / stake), 6),
        })

    if round(sum(item["formal_stake_attributed"] for item in per_match), 2) != formal["stake"]:
        raise ValueError("per-match stake attribution does not reconcile")
    if round(sum(item["formal_payout_attributed"] for item in per_match), 2) != formal["payout"]:
        raise ValueError("per-match payout attribution does not reconcile")

    contrarian = {
        "plans": 3, "hits": 2, "stake": 6.0, "payout": 8.4,
        "net": 2.4, "roi": 0.4,
        "details": [
            "001朝鲜女(-1)让胜@2.10命中：投入2.00，返奖4.20",
            "007日本女(-2)让负@2.24未中（实际让平）：投入2.00，返奖0.00",
            "014保加利亚(-1)让负@2.10命中：投入2.00，返奖4.20",
        ],
    }
    # The late SAFE ticket is identical to a formal ticket and is excluded here to
    # prevent double accounting. Fixed-odds and contrarian tickets are separate too.
    displayed = {
        "plans": 13, "hits": 3, "stake": 182.0, "payout": 73.81,
        "net": -108.19, "roi": -0.594451,
        "details": [
            "16:05顺势观察（004客胜+007主胜）命中：投入50.00，返奖62.16",
            "16:05防冷复式命中1注（005客胜+003客胜）：总投入8.00，返奖4.32",
            "21:06防冷复式命中1注（012客胜+008客胜）：总投入8.00，返奖7.33",
            "其余10组未中；21:06 SAFE与正式稳健票完全相同，已从本项剔除以防重复计算",
        ],
    }

    audit = {
        "schema_version": 1,
        "sales_day": DAY,
        "status": "completed",
        "completed_at": NOW,
        "official_result_coverage": "15/15",
        "final_prediction_coverage": "15/15",
        "post_lock_backfill": False,
        "spf_primary": {"hits": spf_hits, "total": 15, "accuracy": round(spf_hits / 15, 6)},
        "rq_primary": {"hits": rq_hits, "total": 15, "accuracy": round(rq_hits / 15, 6)},
        "formal": formal,
        "fixed_odds_shadow": fixed,
        "contrarian_shadow": contrarian,
        "displayed_shadow_excluding_formal_fixed_and_contrarian": displayed,
        "per_match": per_match,
        "attribution_method": "Each two-leg formal ticket is split 50/50 by stake; payout cents are split deterministically and reconcile to ledger totals.",
        "sources": audit_files + [
            "data/manual/sporttery_results_2026-09-29_sales_window.csv",
            "data/manual/betting_plan_ledger.csv",
            "data/manual/fixed_odds_shadow_ledger.csv",
        ],
        "production_ledger_sha256": hashlib.sha256((ROOT / "data/manual/betting_plan_ledger.csv").read_bytes()).hexdigest(),
        "supabase_sync": "not_authorized_for_2026-09-29",
    }
    AUDIT_PATH.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 2026-09-29 体彩全期逐场复盘", "",
        f"完成时间：{NOW}。官方90分钟赛果15/15，赛前终版覆盖15/15；不做赛后回填。", "",
        "逐场正式金额采用组合票等额归因：二串一的投入按每腿50%分摊，返奖按分精确拆分，逐场合计与正式台账完全一致。", "",
        "## 逐场结果、主方向与正式金额归因", "",
        "|编号|比赛|比分|让球|SPF结果/主方向|让球结果/主方向|正式投入|返奖|净收益|ROI|",
        "|---|---|---:|---:|---|---|---:|---:|---:|---:|",
    ]
    for item in per_match:
        spf = f'{item["spf_result"]} / {item["primary"]}（{"中" if item["primary_hit"] else "未中"}）'
        rq = f'{item["rqspf_result"]} / {item["rq_primary"]}（{"中" if item["rq_primary_hit"] else "未中"}）'
        roi = "不适用" if item["formal_roi_attributed"] is None else f'{item["formal_roi_attributed"]:.2%}'
        lines.append(
            f'|{item["match_number"]}|{item["match"]}|{item["score"]}|{item["handicap"]}|{spf}|{rq}|'
            f'{item["formal_stake_attributed"]:.2f}|{item["formal_payout_attributed"]:.2f}|'
            f'{item["formal_net_attributed"]:+.2f}|{roi}|'
        )
    lines += [
        "", "## 正式、固定赔率影子和其他观察（严格分开）", "",
        f'- 正式方案：{formal["plans"]}组，命中{formal["hits"]}组；投入{formal["stake"]:.2f}元、返奖{formal["payout"]:.2f}元、净收益{formal["net"]:+.2f}元、ROI {formal["roi"]:.2%}。四张二串一全部命中。',
        f'- 固定赔率影子：{fixed["plans"]}组，命中{fixed["hits"]}组；虚拟投入{fixed["stake"]:.2f}元、返奖{fixed["payout"]:.2f}元、净收益{fixed["net"]:+.2f}元、ROI {fixed["roi"]:.2%}。',
        f'- 邪修影子：{contrarian["plans"]}组，命中{contrarian["hits"]}组；虚拟投入{contrarian["stake"]:.2f}元、返奖{contrarian["payout"]:.2f}元、净收益{contrarian["net"]:+.2f}元、ROI {contrarian["roi"]:.2%}。',
        "  - " + "；".join(contrarian["details"]),
        f'- 其余展示影子：{displayed["plans"]}组，命中{displayed["hits"]}组；虚拟投入{displayed["stake"]:.2f}元、返奖{displayed["payout"]:.2f}元、净收益{displayed["net"]:+.2f}元、ROI {displayed["roi"]:.2%}。',
        "  - " + "；".join(displayed["details"]),
        "", "## 结论", "",
        f"- SPF赛前主方向命中{spf_hits}/15（{spf_hits/15:.2%}），让球主方向命中{rq_hits}/15（{rq_hits/15:.2%}）。",
        "- 正式方案四票全中，但样本很小；不得据此提高仓位或采用倍投。",
        "- 固定赔率影子与邪修影子只作研究，不能追认为真实投注收益。",
        "- 捷报数据只用于赛前外盘影子对照；结算以体彩官方90分钟赛果为准。",
        "- 未获该销售日Supabase同步授权，本次只更新本地赛果、台账、复盘报告和控制器状态。", "",
        f"结构化审计：`{AUDIT_PATH.relative_to(ROOT).as_posix()}`", "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_review_20260929_after_final_001",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-29销售日13:00逐场复盘",
        "last_completed_at": NOW,
        "last_stage_status": "completed_review_15_of_15_formal_4_of_4",
        "last_stage_artifact": REPORT_PATH.relative_to(ROOT).as_posix(),
        "last_reviewed_sales_day": DAY,
        "last_review_artifact": REPORT_PATH.relative_to(ROOT).as_posix(),
        "next_required_stage": "2026-09-30 17:00终版分析002",
        "next_required_at": "2026-09-30T17:00:00+08:00",
        "next_dynamic_task_key": "2026-09-30|18:30|终版分析",
        "next_dynamic_task_at": "2026-09-30T17:00:00+08:00",
        "pending_reschedule": True,
        "pending_reschedule_reason": "fixed heartbeat remains active; next registry task is 002 at 17:00",
    })
    state.pop("pending_review_settlement", None)
    state["review_20260929"] = {
        "status": "completed",
        "completed_at": NOW,
        "official_result_coverage": "15/15",
        "final_prediction_coverage": "15/15",
        "formal": formal,
        "fixed_shadow": fixed,
        "contrarian_shadow": contrarian,
        "displayed_shadow_excluding_formal_fixed_and_contrarian": displayed,
        "report": REPORT_PATH.relative_to(ROOT).as_posix(),
        "audit": AUDIT_PATH.relative_to(ROOT).as_posix(),
        "supabase_sync": "not_authorized_for_2026-09-29",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "official": "15/15", "spf": f"{spf_hits}/15", "rqspf": f"{rq_hits}/15",
        "formal": formal, "fixed": fixed, "contrarian": contrarian, "displayed": displayed,
    }, ensure_ascii=True))


if __name__ == "__main__":
    main()
