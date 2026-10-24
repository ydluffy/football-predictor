from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-29T21:06:05+08:00"
REPORT = "artifacts/betting/sporttery_final_analysis_2026-09-29_2106_008-015.md"
AUDIT = "artifacts/data/sporttery_final_analysis_2026-09-29_2106_008-015.json"
STRATEGY = "artifacts/data/production_strategy_2026-09-29_2106_008-015.json"
PLANS = "artifacts/data/production_strategy_plans_2026-09-29_2106_008-015.csv"
ORCHESTRATION = "artifacts/data/final_orchestration_validation_2026-09-29_2106_008-015.json"
FORMAL_LEDGER = "data/manual/betting_plan_ledger.csv"
FIXED_LEDGER = "data/manual/fixed_odds_shadow_ledger.csv"


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def rows(path: str) -> list[dict[str, str]]:
    with (ROOT / path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def append_unique(path: str, row: dict[str, str]) -> bool:
    target = ROOT / path
    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        existing = {item["plan_id"] for item in reader}
    if row["plan_id"] in existing:
        return False
    assert fields is not None
    with target.open("a", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=fields).writerow(row)
    return True


def main() -> None:
    strategy = load(STRATEGY)
    orchestration = load(ORCHESTRATION)
    audit = load(AUDIT)
    if strategy.get("production_plan_rows") != 2 or not orchestration.get("ok"):
        raise ValueError("strategy/orchestration mismatch")

    all_plans = rows(PLANS)
    formal = [p for p in all_plans if p["is_shadow"].lower() == "false"]
    fixed = next(p for p in all_plans if p["plan_id"] == "MULTI_PLAY_FIXED_ODDS_SHADOW")
    if {p["plan_id"] for p in formal} != {"MULTI_PLAY_SAFE", "MULTI_PLAY_VALUE"}:
        raise ValueError("expected SAFE and VALUE formal plans")

    ids = {
        "MULTI_PLAY_SAFE": "SPORTTERY_20260929_008_015_SAFE",
        "MULTI_PLAY_VALUE": "SPORTTERY_20260929_008_015_VALUE",
    }
    added: list[str] = []
    formal_records: list[dict[str, object]] = []
    for plan in formal:
        plan_id = ids[plan["plan_id"]]
        if append_unique(FORMAL_LEDGER, {
            "date": "2026-09-29", "time_window": "21:06-21:45", "plan_id": plan_id,
            "plan_type": plan["plan_type"], "selections": plan["selections"],
            "stake": f'{float(plan["total_stake"]):.2f}',
            "estimated_odds": f'{float(plan["estimated_odds_min"]):.4f}',
            "actual_odds": "", "result": "待赛", "payout": "", "net_profit": "", "roi": "",
            "review_note": "21:45硬锁前冻结；每组本金100元；正式策略及编排校验通过",
        }):
            added.append(plan_id)
        formal_records.append({
            "plan_id": plan_id, "plan_type": plan["plan_type"], "selections": plan["selections"],
            "stake": float(plan["total_stake"]), "estimated_odds": float(plan["estimated_odds_min"]),
            "estimated_payout": float(plan["estimated_payout_min"]),
        })

    fixed_id = "FIXED_ODDS_SHADOW_20260929_21_06_008_015"
    fixed_added = append_unique(FIXED_LEDGER, {
        "date": "2026-09-29", "time_window": "21:06-21:45", "plan_id": fixed_id,
        "plan_type": "固定赔率观察/影子", "selections": fixed["selections"],
        "stake": f'{float(fixed["total_stake"]):.2f}',
        "estimated_odds": f'{float(fixed["estimated_odds_min"]):.4f}',
        "actual_odds": "", "result": "待赛", "payout": "", "net_profit": "", "roi": "",
        "review_note": "固定赔率影子；与正式及邪修分开；不进入正式投注台账",
    })

    audit.update({
        "formal_plans": formal_records,
        "formal_plan_reason": "008-015正式策略生成稳健与价值各一组，并通过门禁与编排校验",
        "production_strategy_executed": True,
        "production_strategy_audit": STRATEGY,
        "production_plan_rows": 2,
        "production_ledger_write_performed": bool(added),
        "production_ledger_plan_ids": list(ids.values()),
        "orchestration_validation": orchestration,
        "fixed_odds_shadow": {
            "status": "recorded" if fixed_added else "already_recorded",
            "plan_id": fixed_id, "selection": fixed["selections"],
            "virtual_stake": float(fixed["total_stake"]),
            "odds": float(fixed["estimated_odds_min"]), "ledger": FIXED_LEDGER,
            "production_ledger_write_performed": False,
        },
        "external_odds": {
            "primary_source": "the_odds_api", "primary_status": "quota_insufficient",
            "quota_remaining": 1, "estimated_route_cost": 12,
            "effective_source": "nowscore", "effective_status": "available_via_nowscore",
            "captured_at": "2026-09-29T21:08:24+08:00", "mapped_matches_all_day": 15,
            "captured_matches_batch": 8, "quote_rows_batch": 816,
            "asian_outer_rows_batch": 136, "research_eligible_rows_batch": 104,
            "failures": [], "production_model_feature_ready": False,
            "per_match": {
                "008": "13 books Scotland +0.5, 1 at +0.75",
                "009": "13 books Czechia +1.5, 1 at +1.75",
                "010": "1 book Slovenia -0.5, 12 at -0.75",
                "011": "5 books Slovakia -1.5, 7 at -1.75",
                "012": "1 book level, 11 at Luxembourg +0.25",
                "013": "1 book Spain -1.5, 13 at -2",
                "014": "1 book Bulgaria -0.5, 11 at -0.75",
                "015": "11 books USA -1, 2 at -1.25",
            },
        },
    })
    (ROOT / AUDIT).write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_path = ROOT / REPORT
    report = report_path.read_text(encoding="utf-8")
    report = report.replace(
        "外盘：鉴权探针HTTP 200，密钥有效，但当前仅余1 credit，不足以执行路由后的多市场刷新；本批0映射并排除。没有统一可核验的首发、伤停、xG或旅行负荷。",
        "外盘：The Odds API仅余1 credit，完整路由预计12 credits，未发送付费请求；捷报后备已完成本批8/8唯一映射并留存赛前亚洲盘。该数据只作研究对照，未升级为生产模型特征；没有统一可核验的首发、伤停、xG或旅行负荷。",
    )
    report = report.replace(
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。",
        "已执行正式策略并通过编排校验：稳健方案为013西班牙主胜 + 011斯洛伐克主胜，本金100元，估算赔率1.2987；价值方案为011斯洛伐克主胜 + 009英格兰客胜，本金100元，估算赔率1.3923。两组均已在21:45硬锁前写入正式模拟台账。",
    )
    report += """

## 内外盘终版对照

- The Odds API仅余1 credit，预计完整路由12 credits，未发起付费赔率请求。
- 捷报后备本批8/8映射成功，共104条赛前研究有效报价；只作影子对照，不作为生产模型特征。
- 008苏格兰主流+0.5；009捷克主流+1.5；010斯洛文尼主流-0.75；011斯洛伐克主流-1.75。
- 012卢森堡主流+0.25；013西班牙主流-2；014保加利亚主流-0.75；015美国主流-1。

## 冻结结论

- 正式稳健：013 西班牙主胜 + 011 斯洛伐克主胜；本金100元，估算赔率1.2987，估算返奖129.87元。
- 正式价值：011 斯洛伐克主胜 + 009 英格兰客胜；本金100元，估算赔率1.3923，估算返奖139.23元。
- 正式总投入200元；008和012未通过正式筛选，其余场次保留在逐场分析中。
- 固定赔率影子：008瑞士客胜 + 010斯洛文尼主胜 + 012冰岛客胜 + 014保加利亚主胜；虚拟本金2元，估算赔率8.1772，独立登记。
- 邪修方案仍仅作理论影子，不写正式台账、不倍投、不追损。
"""
    report_path.write_text(report, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-29.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    targets = {"2026-09-29|02:45|终版分析", "2026-09-29|08:00|终版分析"}
    updated = 0
    for task in registry["tasks"]:
        if task["key"] in targets:
            task.update({
                "status": "completed", "updated_at": NOW, "completed_at": NOW,
                "completion_status": "completed_ready_two_formal_safe_value_fixed_shadow_nowscore_available",
                "artifact": AUDIT, "report": REPORT, "production_plan_rows": 2,
                "production_ledger_write_performed": bool(added),
                "production_plan_ids": list(ids.values()), "formal_total_stake": 200.0,
                "fixed_odds_shadow_rows": 1, "fixed_odds_shadow_plan_id": fixed_id,
            })
            updated += 1
    if updated != 2:
        raise ValueError(f"expected two registry tasks, updated {updated}")
    registry["updated_at"] = NOW
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_final_008_015_two_formal_daily_complete",
        "last_heartbeat_at": NOW, "last_completed_stage": "2026-09-29 21:00终版批次008-015及晚间兜底",
        "last_completed_at": NOW, "last_stage_status": "completed_ready_two_formal_fixed_shadow_nowscore_available",
        "last_stage_artifact": REPORT, "last_ledger_write_at": NOW,
        "inner_outer_alignment_status": "2026-09-29_2108_primary_quota_insufficient_nowscore_batch8_of8",
        "next_dynamic_task_key": None, "next_dynamic_task_at": None,
        "next_required_stage": "2026-09-30 10:00开售前预扫描",
        "next_required_at": "2026-09-30T10:00:00+08:00",
    })
    state["final_20260929_008_015"] = {
        "status": "completed", "completed_at": NOW, "scope": "008-015",
        "official_captured_at": NOW, "gate": "READY_FOR_FINAL_ANALYSIS",
        "formal_strategy_executed": True, "formal_plan_count": 2,
        "formal_plan_ids": list(ids.values()), "formal_total_stake": 200.0,
        "fixed_odds_shadow_count": 1, "fixed_odds_shadow_plan_id": fixed_id,
        "fixed_odds_shadow_stake": 2.0,
        "external_odds": "the_odds_quota_insufficient_nowscore_batch8_of8_research_only",
        "production_ledger_write_performed": bool(added),
        "production_ledger_sha256": hashlib.sha256((ROOT / FORMAL_LEDGER).read_bytes()).hexdigest(),
        "report": REPORT, "review_due_at": "2026-09-30T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-29",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "completed", "scope": "008-015", "formal_added": added,
        "formal_total_stake": 200, "fixed_shadow_added": fixed_added,
        "registry_tasks_updated": updated, "next": "2026-09-30T10:00:00+08:00",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
