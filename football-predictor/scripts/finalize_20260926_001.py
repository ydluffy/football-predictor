from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-26T13:12:00+08:00"


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def main() -> None:
    report_path = ROOT / "artifacts/betting/sporttery_final_analysis_2026-09-26_1310_001.md"
    audit_path = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-26_1310_001.json"
    strategy_path = ROOT / "artifacts/data/sporttery_strategy_2026-09-26_1310_001.json"
    orchestration_path = ROOT / "artifacts/data/sporttery_final_orchestration_2026-09-26_1310_001.json"
    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    orchestration = json.loads(orchestration_path.read_text(encoding="utf-8"))
    assert strategy["production_plan_rows"] == 0 and orchestration["ok"] is True
    reason = (
        "production strategy executed with zero eligible rows: 001 favorite probability 0.4083 is below 0.52, "
        "favorite odds 2.17 exceed 1.85, no model-backed handicap edge, and a one-match batch cannot form a legal two-leg formal combination"
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit.update({
        "formal_plan_reason": reason,
        "production_strategy_executed": True,
        "production_strategy_audit": rel(strategy_path),
        "production_plan_rows": 0,
        "production_ledger_write_performed": False,
        "production_ledger_write_reason": reason,
        "orchestration_validation": orchestration,
        "external_odds": {
            "primary_source": "the_odds_api", "primary_status": "quota_insufficient",
            "effective_source": "nowscore", "effective_status": "available_via_nowscore",
            "captured_at": "2026-09-26T13:08:43+08:00", "mapped_matches": 23,
            "batch_match_mapped": True, "research_eligible_rows_all_matches": 312,
            "production_model_feature_ready": False,
        },
    })
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = report_path.read_text(encoding="utf-8")
    report = report.replace(
        "外盘：鉴权探针HTTP 200，密钥有效，但当前仅余1 credit，不足以执行路由后的多市场刷新；本批0映射并排除。没有统一可核验的首发、伤停、xG或旅行负荷。",
        "外盘：The Odds API仅余1 credit，低于预计12 credits，未发送付费请求；捷报后备已唯一映射001，并作为赛前对照证据留档，但未直接升级为生产模型特征。没有统一可核验的首发、伤停、xG或旅行负荷。",
    )
    report = report.replace(
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。",
        "已执行正式策略并通过编排校验。正式稳健0组、正式价值0组、正式台账新增0行：001市场热门概率0.4083低于0.52、赔率2.17高于1.85、无模型支持的让球优势，且单场批次不能组成合法两腿正式组合；不是授权或外盘闸门拦截。",
    )
    report += """

## 冻结结论

- 正式方案0组，正式投入0元；不为凑方案降低门槛。
- 固定赔率影子0组；单场无法组成6—10倍组合。
- 邪修影子只作理论观察，不写正式投注台账，不倍投、不追损。
"""
    report_path.write_text(report, encoding="utf-8")
    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-26.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for task in registry["tasks"]:
        if task["key"] == "2026-09-26|14:00|终版分析":
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
        "status": "completed_final_001_zero_formal",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-26 12:30终版批次001",
        "last_completed_at": NOW,
        "last_stage_status": "completed_001_ready_strategy_zero_formal_nowscore_available",
        "last_stage_artifact": rel(report_path),
        "next_required_stage": "2026-09-25销售日13:00复盘",
        "next_required_at": "2026-09-26T13:00:00+08:00",
        "next_dynamic_task_key": "2026-09-26|16:00|终版分析",
        "next_dynamic_task_at": "2026-09-26T14:30:00+08:00",
    })
    state["final_20260926_001"] = {
        "status": "completed", "completed_at": NOW, "scope": "001",
        "formal_strategy_executed": True, "formal_plan_count": 0,
        "formal_reason": reason, "shadow_scheme_count": len(audit.get("shadow_schemes", [])),
        "external_odds": "the_odds_quota_insufficient_nowscore_mapped1_of1",
        "production_ledger_write_performed": False, "report": rel(report_path),
        "review_due_at": "2026-09-27T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-26",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "scope": "001", "formal_rows": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
