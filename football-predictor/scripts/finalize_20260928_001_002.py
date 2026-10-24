from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-28T17:06:34+08:00"
REPORT = "artifacts/betting/sporttery_final_analysis_2026-09-28_1706_001-002.md"
AUDIT = "artifacts/data/sporttery_final_analysis_2026-09-28_1706_001-002.json"
STRATEGY = "artifacts/data/production_strategy_2026-09-28_1706_001-002.json"
ORCHESTRATION = "artifacts/data/final_orchestration_validation_2026-09-28_1706_001-002.json"


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def main() -> None:
    audit = load(AUDIT)
    strategy = load(STRATEGY)
    orchestration = load(ORCHESTRATION)
    if strategy["production_plan_rows"] != 0 or not orchestration["ok"]:
        raise ValueError("final strategy artifacts are not internally consistent")

    reason = (
        "production_strategy_executed_with_zero_eligible_rows; 001 passes the market favorite screen but is the only "
        "qualified leg; 002 favorite probability is below 0.52, odds exceed 1.85, and neither match has a model-backed "
        "handicap edge, so no legal two-leg formal safe/value plan exists"
    )
    audit.update({
        "formal_plans": [],
        "formal_plan_reason": reason,
        "production_strategy_audit": STRATEGY,
        "production_strategy_executed": True,
        "production_plan_rows": 0,
        "production_ledger_write_performed": False,
        "orchestration_validation": orchestration,
        "fixed_odds_shadow": {"status": "no_action", "reason": "no_6_to_10_odds_combination_generated"},
        "external_odds": {
            "primary_source": "the_odds_api",
            "primary_status": "quota_insufficient",
            "quota_remaining": 1,
            "estimated_route_cost": 12,
            "effective_source": "nowscore",
            "effective_status": "available_via_nowscore",
            "mapped_matches_all_day": 8,
            "mapped_matches_batch": 2,
            "research_eligible_rows_all_day": 109,
            "per_match": {
                "001": "Nowscore Japan -1.75 at 12 books and -1.5 at 2; deeper than Sporttery -1 and supportive of Japan, but price balance still requires cover-risk discipline",
                "002": "Nowscore Korea draw-no-bet/0 at 13 books and -0.5 at 1; much shallower than Sporttery -1 and supports the Sporttery handicap-away protection",
            },
            "production_model_feature_ready": False,
        },
    })
    (ROOT / AUDIT).write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_path = ROOT / REPORT
    report = report_path.read_text(encoding="utf-8")
    report = report.replace(
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。",
        "已按每组100元规则执行正式策略并通过编排校验。稳健正式0组、价值正式0组、正式台账新增0行：001通过热门筛选但只有一个合格腿；002热门概率低于0.52、赔率高于1.85，且两场均无模型让球支持，无法组成合法二串一。不是授权闸门拦截。",
    )
    report += """

## 内外盘终版对照

- 主来源 The Odds API：仅余1 credit，完整路由预计12 credits，状态 `quota_insufficient`，未发送付费赔率请求。
- 捷报后备：当日8/8唯一映射、109条赛前研究有效报价、失败0；本批2/2覆盖。该数据只作影子对照，未升级为生产模型特征。
- 001 日本 vs 委内瑞拉：捷报12家公司日本-1.75、2家公司-1.5，深于体彩-1；方向支持日本，但深盘价格仍提示严格区分主胜与穿盘。体彩11:05至17:06主胜1.18→1.13，让胜1.71→1.56，主队继续升温。
- 002 韩国 vs 乌拉圭：捷报13家公司韩国0盘、1家公司-0.5，明显浅于体彩-1；不支持把韩国穿盘作为正式腿。体彩胜平负和让球赔率较11:05无变化。

## 正式与影子冻结状态

- 正式稳健/价值：0组，正式投入0元；正式策略已实际执行，原因是合格腿不足和无模型让球支持。
- 固定赔率影子：无6–10倍合格组合，未写固定赔率影子台账。
- 邪修影子：002韩国(-1)让负@1.47，虚拟本金2元；单关资格未核验，只作观察，不倍投、不追损。
- 其余观察方案：顺势50元、让球结构20元、防冷复式8元、总进球8元、比分8元、半全场2元，均与正式台账分开。
"""
    report_path.write_text(report, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-28.json"
    registry = load("artifacts/data/sporttery_task_registry_2026-09-28.json")
    for task in registry["tasks"]:
        if task["key"] == "2026-09-28|18:25-19:00|终版分析":
            task.update({
                "status": "completed",
                "updated_at": NOW,
                "completed_at": NOW,
                "completion_status": "completed_ready_strategy_zero_formal_nowscore_available",
                "artifact": AUDIT,
                "report": REPORT,
                "production_plan_rows": 0,
                "production_ledger_write_performed": False,
                "fixed_odds_shadow_rows": 0,
            })
    registry["updated_at"] = NOW
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = load("artifacts/data/football_automation_controller_state.json")
    state.update({
        "status": "completed_final_001_002_zero_formal_nowscore_available",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-28 16:55终版批次001-002",
        "last_completed_at": NOW,
        "last_stage_status": "completed_001_002_ready_strategy_zero_formal_nowscore_available",
        "last_stage_artifact": REPORT,
        "inner_outer_alignment_status": "2026-09-28_1708_primary_quota_insufficient_nowscore_mapped8_of8_research_rows109",  # pragma: allowlist secret - non-secret status or character set
        "next_dynamic_task_key": "2026-09-28|00:00|终版分析",
        "next_dynamic_task_at": "2026-09-28T21:00:00+08:00",
        "next_required_stage": "2026-09-28 21:00终版分析003及004-008",
        "next_required_at": "2026-09-28T21:00:00+08:00",
        "pending_reschedule": True,
        "pending_reschedule_reason": "automation_update interface unavailable; fixed heartbeat remains active and registry tasks remain pending_schedule",
    })
    state["final_20260928_001_002"] = {
        "status": "completed",
        "completed_at": NOW,
        "scope": "001-002",
        "official_captured_at": NOW,
        "gate": "READY_FOR_FINAL_ANALYSIS",
        "formal_strategy_executed": True,
        "formal_plan_count": 0,
        "formal_reason": reason,
        "fixed_odds_shadow_count": 0,
        "observation_scheme_count": 7,
        "external_odds": "the_odds_quota_insufficient_nowscore_mapped2_of2_research_only",
        "production_ledger_write_performed": False,
        "report": REPORT,
        "review_due_at": "2026-09-29T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-28",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "scope": "001-002", "formal": 0, "fixed_shadow": 0, "next": "2026-09-28T21:00:00+08:00"}, ensure_ascii=True))


if __name__ == "__main__":
    main()
