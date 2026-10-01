from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-28T21:06:38+08:00"
REPORT = "artifacts/betting/sporttery_final_analysis_2026-09-28_2106_003-008.md"
AUDIT = "artifacts/data/sporttery_final_analysis_2026-09-28_2106_003-008.json"
STRATEGY = "artifacts/data/production_strategy_2026-09-28_2106_003-008.json"
ORCHESTRATION = "artifacts/data/final_orchestration_validation_2026-09-28_2106_003-008.json"
FIXED = "artifacts/data/fixed_odds_shadow_2026-09-28_2106_003-008.json"
FORMAL_LEDGER = "data/manual/betting_plan_ledger.csv"


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def main() -> None:
    audit = load(AUDIT)
    strategy = load(STRATEGY)
    orchestration = load(ORCHESTRATION)
    fixed = load(FIXED)
    if strategy["production_plan_rows"] != 0 or not orchestration["ok"]:
        raise ValueError("final strategy artifacts are not internally consistent")
    if fixed["status"] not in {"recorded", "already_recorded"}:
        raise ValueError("fixed-odds shadow was not frozen")

    reason = (
        "production_strategy_executed_with_zero_eligible_combinations; 005 is the only leg passing the formal favorite "
        "screen; 003/004/006/008 are below 0.52 with odds above 1.85, 007 is below 0.52, and none has a "
        "model-backed handicap edge, so no legal two-leg formal safe/value plan exists"
    )
    audit.update({
        "formal_plans": [],
        "formal_plan_reason": reason,
        "production_strategy_audit": STRATEGY,
        "production_strategy_executed": True,
        "production_plan_rows": 0,
        "production_ledger_write_performed": False,
        "orchestration_validation": orchestration,
        "fixed_odds_shadow": {
            "status": "recorded",
            "plan_id": fixed["plan_id"],
            "virtual_stake": 2,
            "odds": fixed["odds"],
            "selection": fixed["selection"],
            "ledger": fixed["ledger"],
            "production_ledger_write_performed": False,
        },
        "external_odds": {
            "primary_source": "the_odds_api",
            "primary_status": "quota_insufficient",
            "quota_remaining": 1,
            "estimated_route_cost": 12,
            "effective_source": "nowscore",
            "effective_status": "available_via_nowscore",
            "mapped_matches_all_day": 8,
            "captured_matches_batch": 6,
            "research_eligible_rows_batch": 81,
            "failures": 0,
            "per_match": {
                "003": "13 books at level ball/0, materially shallower than Sporttery Armenia -1",
                "004": "13 books at level ball/0 and 1 at Turkey +0.25, shallower than Sporttery Turkey +1",
                "005": "13 books at Belgium +0.5 and 1 at +0.75, broadly supports France but not a full-goal margin",
                "006": "12 books at Romania -0.25 and 1 at level ball/0, shallower than Sporttery Romania -1",
                "007": "12 books at Sweden -0.5 and 2 at -0.25, shallower than Sporttery Sweden -1",
                "008": "13 books at level ball/0, materially shallower than Sporttery Northern Ireland +1",
            },
            "production_model_feature_ready": False,
        },
    })
    (ROOT / AUDIT).write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_path = ROOT / REPORT
    report = report_path.read_text(encoding="utf-8")
    report = report.replace(
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。",
        "已按每组100元规则执行正式策略并通过编排校验。稳健正式0组、价值正式0组、正式台账新增0行：005是唯一通过正式热门筛选的腿；003/004/006/008热门概率低于0.52且赔率高于1.85，007热门概率也低于0.52，六场均无模型让球支持，无法组成合法二串一。不是授权闸门拦截。",
    )
    report += """

## 内外盘终版对照

- 主来源 The Odds API：仅余1 credit，完整路由预计12 credits，状态 `quota_insufficient`，未发送付费赔率请求。
- 捷报后备：当日8/8唯一映射；本批当前在售6/6抓取成功，81条赛前研究有效报价，失败0。该数据只作影子对照，未升级为生产模型特征。
- 003：捷报13家公司平手盘，明显浅于体彩亚美尼亚-1；支持体彩让负保护，不支持把主队穿盘纳入正式方案。
- 004：捷报13家公司平手、1家公司土耳其+0.25，明显浅于体彩土耳其+1；外盘没有给意大利深让确认。
- 005：捷报13家公司比利时+0.5、1家公司+0.75，方向偏法国但未到一球；法国客胜是唯一通过热门筛选的正式腿。
- 006：捷报12家公司罗马尼亚-0.25、1家公司平手，浅于体彩罗马尼亚-1；主胜与穿盘须分开。
- 007：捷报12家公司瑞典-0.5、2家公司-0.25，浅于体彩瑞典-1；瑞典主胜概率0.5148仍低于正式0.52门槛。
- 008：捷报13家公司平手盘，明显浅于体彩北爱尔兰+1；不支持把匈牙利客胜视为低风险正式腿。

## 正式与影子冻结状态

- 正式稳健/价值：0组，正式投入0元；正式策略已实际执行，原因是只有005一个合格腿且无模型让球支持。
- 固定赔率影子：004意大利客胜 + 006罗马尼亚主胜 + 007瑞典主胜，虚拟本金2元，组合赔率7.9086；已独立写入固定赔率影子台账，未写正式台账。
- 邪修影子：008北爱尔兰(+1)让胜@1.43，虚拟本金2元；单关资格未核验，只作观察，不倍投、不追损。
- 其余观察方案继续与正式、固定赔率和邪修影子分开保存。
"""
    report_path.write_text(report, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-28.json"
    registry = load("artifacts/data/sporttery_task_registry_2026-09-28.json")
    target_keys = {"2026-09-28|00:00|终版分析", "2026-09-28|02:45|终版分析"}
    updated = 0
    for task in registry["tasks"]:
        if task["key"] in target_keys:
            task.update({
                "status": "completed",
                "updated_at": NOW,
                "completed_at": NOW,
                "completion_status": "completed_ready_strategy_zero_formal_fixed_shadow_recorded_nowscore_available",
                "artifact": AUDIT,
                "report": REPORT,
                "production_plan_rows": 0,
                "production_ledger_write_performed": False,
                "fixed_odds_shadow_rows": 1,
                "fixed_odds_shadow_plan_id": fixed["plan_id"],
            })
            updated += 1
    if updated != 2:
        raise ValueError(f"expected to update 2 registry tasks, updated {updated}")
    registry["updated_at"] = NOW
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = load("artifacts/data/football_automation_controller_state.json")
    state.update({
        "status": "completed_final_003_008_zero_formal_fixed_shadow_nowscore_available",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-28 21:00终版批次003及004-008",
        "last_completed_at": NOW,
        "last_stage_status": "completed_003_008_ready_strategy_zero_formal_fixed_shadow_nowscore_available",
        "last_stage_artifact": REPORT,
        "inner_outer_alignment_status": "2026-09-28_2108_primary_quota_insufficient_nowscore_batch6_of6_research_rows81",
        "next_dynamic_task_key": None,
        "next_dynamic_task_at": None,
        "next_required_stage": "2026-09-29 10:00开售前预扫描",
        "next_required_at": "2026-09-29T10:00:00+08:00",
        "pending_reschedule": True,
        "pending_reschedule_reason": "fixed 30-minute heartbeat remains the long-term fallback; no additional desktop task is required",
    })
    state["final_20260928_003_008"] = {
        "status": "completed",
        "completed_at": NOW,
        "scope": "003-008",
        "official_captured_at": NOW,
        "gate": "READY_FOR_FINAL_ANALYSIS",
        "formal_strategy_executed": True,
        "formal_plan_count": 0,
        "formal_reason": reason,
        "fixed_odds_shadow_count": 1,
        "fixed_odds_shadow_plan_id": fixed["plan_id"],
        "fixed_odds_shadow_stake": 2,
        "fixed_odds_shadow_odds": fixed["odds"],
        "observation_scheme_count": 10,
        "external_odds": "the_odds_quota_insufficient_nowscore_batch6_of6_research_only",
        "production_ledger_write_performed": False,
        "production_ledger_sha256": hashlib.sha256((ROOT / FORMAL_LEDGER).read_bytes()).hexdigest(),
        "report": REPORT,
        "review_due_at": "2026-09-29T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-28",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "completed",
        "scope": "003-008",
        "formal": 0,
        "fixed_shadow": 1,
        "fixed_plan_id": fixed["plan_id"],
        "registry_tasks_updated": updated,
        "next": "2026-09-29T10:00:00+08:00",
    }, ensure_ascii=True))


if __name__ == "__main__":
    main()
