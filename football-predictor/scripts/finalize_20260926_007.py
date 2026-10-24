from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-26T17:15:00+08:00"


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def main() -> None:
    report_path = ROOT / "artifacts/betting/sporttery_final_analysis_2026-09-26_1705_007.md"
    audit_path = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-26_1705_007.json"
    strategy_path = ROOT / "artifacts/data/sporttery_final_strategy_2026-09-26_1705_007_audit.json"
    orchestration_path = ROOT / "artifacts/data/sporttery_final_orchestration_2026-09-26_1705_007.json"
    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    orchestration = json.loads(orchestration_path.read_text(encoding="utf-8"))
    assert strategy["production_plan_rows"] == 0 and orchestration["ok"] is True
    reason = (
        "007 favorite probability 0.8048 and odds 1.10 pass the favorite screen, but the batch has only one match, "
        "single-bet eligibility is unverified, and no model-backed handicap edge exists; therefore no legal formal combination can be created"
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit.update({
        "formal_plan_reason": reason,
        "production_strategy_executed": True,
        "production_strategy_audit": rel(strategy_path),
        "production_plan_rows": 0,
        "production_ledger_write_performed": False,
        "orchestration_validation": orchestration,
        "external_odds": {
            "primary_source": "the_odds_api", "primary_status": "quota_insufficient",
            "effective_source": "nowscore", "effective_status": "available_via_nowscore",
            "captured_at": "2026-09-26T17:07:38+08:00", "mapped_matches_all": 23,
            "captured_on_sale_all": 17, "batch_mapped": 1, "batch_captured": 1,
            "quote_rows_all": 1734, "asian_outer_rows_all": 289,
            "research_eligible_rows_all": 232, "failures": [],
            "production_model_feature_ready": False,
        },
    })
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = report_path.read_text(encoding="utf-8")
    report = report.replace(
        "外盘：鉴权探针HTTP 200，密钥有效，但当前仅余1 credit，不足以执行路由后的多市场刷新；本批0映射并排除。没有统一可核验的首发、伤停、xG或旅行负荷。",
        "外盘：The Odds API仅余1 credit，低于预计12 credits，未发送付费请求；捷报后备已完成007唯一映射并留存赛前报价。外盘仅作对照证据，尚未升级为生产模型特征；没有统一可核验的首发、伤停、xG或旅行负荷。",
    )
    report = report.replace(
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。",
        "已执行强制正式策略并通过编排校验。007主胜概率0.8048、赔率1.10虽然通过热门筛选，但本批只有一场、单关资格未核实且没有模型支持的让球优势，无法组成合法正式组合；正式稳健0组、正式价值0组、正式台账新增0行。",
    )
    report += """

## 冻结结论

- 正式方案0组，正式投入0元；不把超低赔单场当作必胜锚点。
- 固定赔率影子0组；单场无法组成6—10倍组合。
- 邪修影子：007(-1)让胜@1.43，虚拟本金2元，只作理论观察，不写正式台账、不倍投、不追损。
- 捷报后备本批覆盖1/1；The Odds API主状态仍为额度不足。
"""
    report_path.write_text(report, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-26.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for task in registry["tasks"]:
        if task["key"] == "2026-09-26|18:30|终版分析":
            task.update({
                "status": "completed", "completed_at": NOW,
                "completion_status": "completed_ready_strategy_zero_formal_nowscore_available",
                "artifact": rel(audit_path), "report": rel(report_path),
                "production_plan_rows": 0, "production_ledger_write_performed": False,
            })
    registry["updated_at"] = NOW
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_final_007_zero_formal",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-26 17:00终版批次007",
        "last_completed_at": NOW,
        "last_stage_status": "completed_007_ready_strategy_zero_formal_nowscore_available",
        "last_stage_artifact": rel(report_path),
        "next_required_stage": "2026-09-26 19:30终版分析008-009",
        "next_required_at": "2026-09-26T19:30:00+08:00",
        "next_dynamic_task_key": "2026-09-26|21:00-22:30|终版分析",
        "next_dynamic_task_at": "2026-09-26T19:30:00+08:00",
        "inner_outer_alignment_status": "2026-09-26_1707_primary_quota_insufficient_nowscore_batch_mapped1_of1",  # pragma: allowlist secret - non-secret status or character set
    })
    state["final_20260926_007"] = {
        "status": "completed", "completed_at": NOW, "scope": "007",
        "formal_strategy_executed": True, "formal_plan_count": 0,
        "formal_reason": reason, "shadow_scheme_count": len(audit.get("shadow_schemes", [])),
        "external_odds": "the_odds_quota_insufficient_nowscore_mapped1_of1",
        "production_ledger_write_performed": False, "report": rel(report_path),
        "review_due_at": "2026-09-27T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-26",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "scope": "007", "formal_rows": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
