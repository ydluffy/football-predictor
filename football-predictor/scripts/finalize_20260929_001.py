from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-29T13:06:55+08:00"
REPORT = "artifacts/betting/sporttery_final_analysis_2026-09-29_1306_001.md"
AUDIT = "artifacts/data/sporttery_final_analysis_2026-09-29_1306_001.json"
STRATEGY = "artifacts/data/production_strategy_2026-09-29_1306_001.json"
ORCHESTRATION = "artifacts/data/final_orchestration_validation_2026-09-29_1306_001.json"


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def main() -> None:
    audit = load(AUDIT)
    strategy = load(STRATEGY)
    orchestration = load(ORCHESTRATION)
    if strategy["production_plan_rows"] != 0 or not orchestration["ok"]:
        raise ValueError("final strategy artifacts are inconsistent")
    reason = (
        "001 passes the formal favorite screen at probability 0.6605 and odds 1.34, but it is the only match in this "
        "batch and the handicap model is blocked outside its training domain; therefore no legal two-leg formal safe/value plan exists"
    )
    audit.update({
        "formal_plans": [],
        "formal_plan_reason": reason,
        "production_strategy_audit": STRATEGY,
        "production_strategy_executed": True,
        "production_plan_rows": 0,
        "production_ledger_write_performed": False,
        "orchestration_validation": orchestration,
        "fixed_odds_shadow": {"status": "no_action", "reason": "single-match batch cannot form a 6-to-10 odds combination"},
        "external_odds": {
            "primary_source": "the_odds_api",
            "primary_status": "quota_insufficient",
            "quota_remaining": 1,
            "estimated_route_cost": 12,
            "effective_source": "nowscore",
            "effective_status": "available_via_nowscore",
            "mapped_matches_all_day": 15,
            "mapped_matches_batch": 1,
            "research_eligible_rows_all_day": 192,
            "per_match": {"001": "12 books North Korea Women -1.25 and 1 book -1.5, deeper than Sporttery -1"},
            "production_model_feature_ready": False,
        },
    })
    (ROOT / AUDIT).write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_path = ROOT / REPORT
    report = report_path.read_text(encoding="utf-8")
    report = report.replace(
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。",
        "已按每组100元规则执行正式策略并通过编排校验。正式稳健0组、价值0组、正式台账新增0行：001主胜概率0.6605、赔率1.34通过热门筛选，但本批只有一个合格腿，且让球模型因超出训练域被阻断，无法组成合法二串一。不是授权闸门拦截。",
    )
    report += """

## 内外盘终版对照

- The Odds API仅余1 credit，完整路由预计12 credits，未发送付费请求。
- 捷报后备当日15/15映射；001有12家公司朝鲜女足-1.25、1家公司-1.5，深于体彩-1，方向支持朝鲜女足，但仍只作影子研究，未升级为生产模型特征。
- 体彩11:05至13:06：主胜1.36→1.34、平4.25→4.50、客胜6.25→6.15；让胜2.15→2.10、让平3.47→3.55、让负2.66→2.70。主胜与让胜略升温，但赢球和穿盘仍须分开。

## 正式与影子冻结状态

- 正式方案0组、正式投入0元；正式策略已实际执行，零方案原因是单场不足以组成合法二串一。
- 固定赔率影子无6—10倍合格组合，未写固定赔率影子台账。
- 邪修影子：001朝鲜女足(-1)让胜@2.10，虚拟本金2元；单关资格未核验，不倍投、不追损，与正式台账分开。
"""
    report_path.write_text(report, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-29.json"
    registry = load("artifacts/data/sporttery_task_registry_2026-09-29.json")
    updated = 0
    for task in registry["tasks"]:
        if task["key"] == "2026-09-29|14:00|终版分析":
            task.update({
                "status": "completed",
                "updated_at": NOW,
                "completed_at": NOW,
                "completion_status": "completed_ready_strategy_zero_formal_single_match_nowscore_available",
                "artifact": AUDIT,
                "report": REPORT,
                "production_plan_rows": 0,
                "production_ledger_write_performed": False,
                "fixed_odds_shadow_rows": 0,
            })
            updated += 1
    if updated != 1:
        raise ValueError("001 registry task not found")
    registry["updated_at"] = NOW
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = load("artifacts/data/football_automation_controller_state.json")
    state.update({
        "status": "completed_final_001_zero_formal_nowscore_available",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-29 12:30终版批次001",
        "last_completed_at": NOW,
        "last_stage_status": "completed_001_ready_strategy_zero_formal_nowscore_available",
        "last_stage_artifact": REPORT,
        "next_dynamic_task_key": "2026-09-29|18:00-18:30|终版分析",
        "next_dynamic_task_at": "2026-09-29T16:30:00+08:00",
        "next_required_stage": "2026-09-29 13:00复盘2026-09-28",
        "next_required_at": "2026-09-29T13:00:00+08:00",
        "pending_reschedule": True,
        "pending_reschedule_reason": "fixed heartbeat remains active; previous-sales-day review is now the earliest due task",
    })
    state["final_20260929_001"] = {
        "status": "completed",
        "completed_at": NOW,
        "scope": "001",
        "official_captured_at": NOW,
        "gate": "READY_FOR_FINAL_ANALYSIS",
        "formal_strategy_executed": True,
        "formal_plan_count": 0,
        "formal_reason": reason,
        "fixed_odds_shadow_count": 0,
        "observation_scheme_count": 1,
        "external_odds": "the_odds_quota_insufficient_nowscore_mapped1_of1_research_only",
        "production_ledger_write_performed": False,
        "production_ledger_sha256": hashlib.sha256((ROOT / "data/manual/betting_plan_ledger.csv").read_bytes()).hexdigest(),
        "report": REPORT,
        "review_due_at": "2026-09-30T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-29",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "scope": "001", "formal": 0, "fixed_shadow": 0, "next": "2026-09-29T13:00:00+08:00"}))


if __name__ == "__main__":
    main()
