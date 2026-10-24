from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-26T20:18:00+08:00"


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def main() -> None:
    report_path = ROOT / "artifacts/betting/sporttery_final_analysis_2026-09-26_2006_008-009.md"
    audit_path = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-26_2006_008-009.json"
    strategy_path = ROOT / "artifacts/data/sporttery_final_strategy_2026-09-26_2006_008-009_audit.json"
    orchestration_path = ROOT / "artifacts/data/sporttery_final_orchestration_2026-09-26_2006_008-009.json"
    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    orchestration = json.loads(orchestration_path.read_text(encoding="utf-8"))
    assert strategy["production_plan_rows"] == 0 and orchestration["ok"] is True
    reason = (
        "008 favorite probability 0.3499 is below 0.52, favorite odds 2.53 exceed 1.85, and there is no model-backed handicap; "
        "009 passes the favorite screen at probability 0.6419 and odds 1.38, but it is the only qualified leg and cannot form a legal formal combination"
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
            "captured_at": "2026-09-26T20:09:01+08:00", "mapped_matches_all": 23,
            "captured_on_sale_all": 16, "batch_mapped": 2, "batch_captured": 2,
            "quote_rows_all": 1632, "asian_outer_rows_all": 272,
            "research_eligible_rows_all": 218, "failures": [],
            "production_model_feature_ready": False,
        },
    })
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = report_path.read_text(encoding="utf-8")
    report = report.replace(
        "外盘：鉴权探针HTTP 200，密钥有效，但当前仅余1 credit，不足以执行路由后的多市场刷新；本批0映射并排除。没有统一可核验的首发、伤停、xG或旅行负荷。",
        "外盘：The Odds API仅余1 credit，低于预计12 credits，未发送付费请求；捷报后备已完成本批2/2唯一映射并留存赛前报价。外盘仅作对照证据，尚未升级为生产模型特征；没有统一可核验的首发、伤停、xG或旅行负荷。",
    )
    report = report.replace(
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。",
        "已执行强制正式策略并通过编排校验。008热门概率0.3499低于0.52、赔率2.53高于1.85且无模型让球优势；009概率0.6419、赔率1.38通过热门筛选，但仅有一个合格腿，无法组成合法正式组合。正式稳健0组、正式价值0组、正式台账新增0行。",
    )
    report += """

## 冻结结论

- 正式方案0组，正式投入0元；不以009超低赔单腿强行拼单。
- 固定赔率影子0组；未找到6—10倍合格组合。
- 邪修影子：008(-1)让负@1.38，虚拟本金2元，只作理论观察，不写正式台账、不倍投、不追损。
- 捷报后备本批覆盖2/2；The Odds API主状态仍为额度不足。
"""
    report_path.write_text(report, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-26.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for task in registry["tasks"]:
        if task["key"] == "2026-09-26|21:00-22:30|终版分析":
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
        "status": "completed_final_008_009_zero_formal",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-26 19:30终版批次008-009",
        "last_completed_at": NOW,
        "last_stage_status": "completed_008_009_ready_strategy_zero_formal_nowscore_available",
        "last_stage_artifact": rel(report_path),
        "next_required_stage": "2026-09-26 22:00终版分析010-023及晚间兜底",
        "next_required_at": "2026-09-26T22:00:00+08:00",
        "next_dynamic_task_key": "2026-09-26|00:00|终版分析",
        "next_dynamic_task_at": "2026-09-26T22:00:00+08:00",
        "inner_outer_alignment_status": "2026-09-26_2009_primary_quota_insufficient_nowscore_batch_mapped2_of2",
    })
    state["final_20260926_008_009"] = {
        "status": "completed", "completed_at": NOW, "scope": "008-009",
        "formal_strategy_executed": True, "formal_plan_count": 0,
        "formal_reason": reason, "shadow_scheme_count": len(audit.get("shadow_schemes", [])),
        "external_odds": "the_odds_quota_insufficient_nowscore_mapped2_of2",
        "production_ledger_write_performed": False, "report": rel(report_path),
        "review_due_at": "2026-09-27T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-26",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "scope": "008-009", "formal_rows": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
