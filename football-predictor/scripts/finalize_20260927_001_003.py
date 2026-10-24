from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_AT = "2026-09-27T16:09:45+08:00"
REPORT = "artifacts/betting/sporttery_final_analysis_2026-09-27_1609_001-003.md"
AUDIT = "artifacts/data/sporttery_final_analysis_2026-09-27_1609_001-003.json"
STRATEGY = "artifacts/data/production_strategy_2026-09-27_1609_001-003.json"
ORCHESTRATION = "artifacts/data/final_orchestration_validation_2026-09-27_1609_001-003.json"
FIXED = "artifacts/data/fixed_odds_shadow_2026-09-27_1609_001-003.json"


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def main() -> None:
    audit = load(AUDIT)
    strategy = load(STRATEGY)
    orchestration = load(ORCHESTRATION)
    fixed = load(FIXED)
    if strategy["production_plan_rows"] != 0 or not orchestration["ok"] or fixed["status"] != "recorded":
        raise ValueError("final artifacts are not internally consistent")

    formal_reason = (
        "production_strategy_executed_with_zero_eligible_rows; all three favorite probabilities are below 0.52; "
        "001 and 003 favorite odds exceed 1.85; no model-backed handicap edge exists"
    )
    audit.update({
        "formal_plans": [],
        "formal_plan_reason": formal_reason,
        "production_strategy_audit": STRATEGY,
        "production_strategy_executed": True,
        "production_plan_rows": 0,
        "production_ledger_write_performed": False,
        "orchestration_validation": orchestration,
        "fixed_odds_shadow": {
            "status": "recorded",
            "plan_id": fixed["plan_id"],
            "selection": fixed["selection"],
            "odds": fixed["odds"],
            "virtual_stake": 2.0,
            "ledger": fixed["ledger"],
            "production_ledger_write_performed": False,
        },
        "external_odds": {
            "primary_source": "the_odds_api",
            "primary_status": "quota_insufficient",
            "quota_remaining": 1,
            "estimated_route_cost": 24,
            "effective_source": "nowscore",
            "effective_status": "available_via_nowscore",
            "mapped_matches": 3,
            "research_eligible_rows_all_9_matches": 125,
            "per_match": {
                "001": "Nowscore consensus home -0.25 (13 books), shallower than Sporttery -1",
                "002": "Nowscore home +0.25 (10 books) / +0.5 (4), shallower than Sporttery +1",
                "003": "Nowscore consensus home -0.25 (13 books), shallower than Sporttery -1",
            },
            "production_model_feature_ready": False,
        },
    })
    (ROOT / AUDIT).write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_path = ROOT / REPORT
    report = report_path.read_text(encoding="utf-8")
    report = report.replace(
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。",
        "已按每组100元规则运行正式策略并通过编排校验。稳健正式0组、价值正式0组、正式台账新增0行：001、002、003的市场隐含热门概率均低于0.52；001、003热门赔率高于1.85，且三场均无模型让球支持。不是授权闸门拦截。",
    )
    report += """

## 内外盘终版对照

- 主来源 The Odds API：仅余1 credit，预计完整路由成本24，状态为 `quota_insufficient`，未发出付费请求。
- 捷报后备：当日9/9唯一映射，共125条赛前研究有效报价；本批001—003均唯一映射。仅作影子对照，不升级为生产模型特征。
- 001 江原FC vs 仁川联：捷报主流江原-0.25（13家公司），明显浅于体彩-1。支持主队轻微优势，但强化一球差/不穿盘保护。
- 002 中国 vs 新西兰：捷报主流中国+0.25（10家公司），另有+0.5（4家），明显浅于体彩+1。外盘仍偏新西兰，但体彩+1让胜保护更强。
- 003 格拉夫 vs 登博思：捷报主流格拉夫-0.25（13家公司），明显浅于体彩-1。支持主队轻微优势，不支持深穿。

## 正式与影子冻结状态

- 正式稳健/价值：0组，每组100元规则已实际执行；正式投入0元。原因是概率、赔率与模型支持门禁，不是授权问题。
- 固定赔率影子：已独立登记1组，2元虚拟本金：001主胜@2.00 + 002客胜@1.85 + 003主胜@1.96，组合赔率7.252。
- 邪修影子：003(-1)让负@1.64，2元虚拟本金；单关资格未核验，只作观察，不计正式台账、不倍投追损。
- 本批按固定心跳35分钟提前窗口于16:09执行，官方快照早于三场开赛，硬锁仍为17:45。
"""
    report_path.write_text(report, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-27.json"
    registry = load("artifacts/data/sporttery_task_registry_2026-09-27.json")
    for task in registry["tasks"]:
        if task["key"] == "2026-09-27|15:00|全9场赔率基线":
            task.update({
                "status": "completed", "updated_at": "2026-09-27T15:12:00+08:00",
                "completed_at": "2026-09-27T15:12:00+08:00",
                "completion_status": "completed_9_match_official_and_nowscore_baseline_no_ledger",
                "artifact": "artifacts/data/sporttery_early_baseline_2026-09-27_1506_001-009.json",
                "report": "artifacts/betting/sporttery_early_baseline_2026-09-27_1506_001-009.md",
                "official_on_sale": 9, "nowscore_mapped": 9, "production_ledger_write_performed": False,
            })
        elif task["key"] == "2026-09-27|16:30|001-003终版":
            task.update({
                "status": "completed", "updated_at": ANALYSIS_AT, "completed_at": ANALYSIS_AT,
                "completion_status": "completed_ready_strategy_zero_formal_fixed_shadow_recorded_nowscore_available",
                "artifact": AUDIT, "report": REPORT, "production_plan_rows": 0,
                "production_ledger_write_performed": False, "fixed_odds_shadow_rows": 1,
            })
    registry["updated_at"] = ANALYSIS_AT
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = load("artifacts/data/football_automation_controller_state.json")
    state.update({
        "status": "completed_final_001_003_zero_formal_fixed_shadow_recorded",
        "last_heartbeat_at": ANALYSIS_AT,
        "last_completed_stage": "2026-09-27 16:30终版批次001-003",
        "last_completed_at": ANALYSIS_AT,
        "last_stage_status": "completed_001_003_ready_strategy_zero_formal_fixed_shadow_recorded_nowscore_available",
        "last_stage_artifact": REPORT,
        "inner_outer_alignment_status": "2026-09-27_1609_primary_quota_insufficient_nowscore_mapped3_of3_research_only",  # pragma: allowlist secret - non-secret status or character set
        "next_dynamic_task_key": "2026-09-27|22:00|004-009终版",
        "next_dynamic_task_at": "2026-09-27T22:00:00+08:00",
        "next_required_stage": "2026-09-27 22:00终版分析004-009",
        "next_required_at": "2026-09-27T22:00:00+08:00",
        "pending_reschedule": True,
        "pending_reschedule_reason": "automation_update interface unavailable; fixed heartbeat remains active and custom registry task remains pending_schedule",
    })
    state["final_20260927_001_003"] = {
        "status": "completed", "completed_at": ANALYSIS_AT, "scope": "001-003",
        "official_captured_at": ANALYSIS_AT, "gate": "READY_FOR_FINAL_ANALYSIS",
        "formal_strategy_executed": True, "formal_plan_count": 0, "formal_reason": formal_reason,
        "fixed_odds_shadow_count": 1, "observation_scheme_count": 9,
        "external_odds": "the_odds_quota_insufficient_nowscore_mapped3_of3_research_only",
        "production_ledger_write_performed": False, "report": REPORT,
        "review_due_at": "2026-09-28T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-27",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "scope": "001-003", "production_plan_rows": 0, "fixed_shadow_rows": 1, "next": "2026-09-27T22:00:00+08:00"}, ensure_ascii=True))


if __name__ == "__main__":
    main()
