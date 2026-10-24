from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-26T15:15:00+08:00"
FIXED_ID = "FIXED_ODDS_SHADOW_20260926_15_05_002_006"


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def main() -> None:
    report_path = ROOT / "artifacts/betting/sporttery_final_analysis_2026-09-26_1505_002-006.md"
    audit_path = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-26_1505_002-006.json"
    strategy_path = ROOT / "artifacts/data/sporttery_final_strategy_2026-09-26_1505_002-006_audit.json"
    plans_path = ROOT / "artifacts/data/sporttery_final_strategy_2026-09-26_1505_002-006_plans.csv"
    orchestration_path = ROOT / "artifacts/data/sporttery_final_orchestration_2026-09-26_1505_002-006.json"
    fixed_ledger = ROOT / "data/manual/fixed_odds_shadow_ledger.csv"

    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    orchestration = json.loads(orchestration_path.read_text(encoding="utf-8"))
    assert strategy["production_plan_rows"] == 0 and orchestration["ok"] is True
    with plans_path.open(encoding="utf-8-sig", newline="") as handle:
        plans = list(csv.DictReader(handle))
    fixed = next(row for row in plans if row["plan_id"] == "MULTI_PLAY_FIXED_ODDS_SHADOW")

    with fixed_ledger.open(encoding="utf-8-sig", newline="") as handle:
        existing = list(csv.DictReader(handle))
    fixed_added = not any(row["plan_id"] == FIXED_ID for row in existing)
    if fixed_added:
        with fixed_ledger.open("a", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerow([
                "2026-09-26", "15:05-15:45", FIXED_ID, "固定赔率观察/影子",
                fixed["selections"], "2.00", fixed["estimated_odds_min"], "", "待赛",
                "", "", "", "15:45硬锁前冻结；仅影子观察；不进入正式投注台账",
            ])

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit.update({
        "formal_plans": [],
        "formal_plan_reason": "mandatory production strategy executed with zero eligible rows; 002-004 probabilities failed the 0.52 threshold and had no model-backed handicap, while 005-006 lacked complete SPF/RQSPF inputs",
        "production_strategy_executed": True,
        "production_strategy_audit": rel(strategy_path),
        "production_plan_rows": 0,
        "production_ledger_write_performed": False,
        "orchestration_validation": orchestration,
        "fixed_odds_shadow_ledger": {
            "plan_id": FIXED_ID,
            "selections": fixed["selections"],
            "stake": 2.0,
            "estimated_odds": float(fixed["estimated_odds_min"]),
            "ledger_added": fixed_added,
        },
        "external_odds": {
            "primary_source": "the_odds_api", "primary_status": "quota_insufficient",
            "effective_source": "nowscore", "effective_status": "available_via_nowscore",
            "captured_at": "2026-09-26T15:10:30+08:00", "mapped_matches_all": 23,
            "captured_on_sale_all": 22, "batch_mapped": 5, "batch_captured": 5,
            "quote_rows_all": 2244, "asian_outer_rows_all": 374,
            "research_eligible_rows_all": 300, "failures": [],
            "production_model_feature_ready": False,
        },
    })
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = report_path.read_text(encoding="utf-8")
    report = report.replace(
        "外盘：鉴权探针HTTP 200，密钥有效，但当前仅余1 credit，不足以执行路由后的多市场刷新；本批0映射并排除。没有统一可核验的首发、伤停、xG或旅行负荷。",
        "外盘：The Odds API仅余1 credit，低于预计12 credits，未发送付费请求；捷报后备已完成本批5/5唯一映射并留存赛前报价。外盘仅作对照证据，尚未升级为生产模型特征；没有统一可核验的首发、伤停、xG或旅行负荷。",
    )
    report = report.replace(
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。",
        "已执行强制正式策略并通过编排校验。正式稳健0组、正式价值0组、正式台账新增0行：002—004概率未达到0.52且没有模型支持的让球优势，005—006缺少完整SPF/RQSPF策略输入；不是授权或外盘闸门拦截。",
    )
    report += f"""

## 冻结结论

- 正式方案0组，正式投入0元；不为凑方案降低生产门槛。
- 固定赔率影子：{fixed['selections']}，虚拟本金2元，组合赔率{fixed['estimated_odds_min']}，已独立登记。
- 邪修影子：006(-1)让负@1.39，虚拟本金2元，只作理论观察；不进入正式台账、不倍投、不追损。
- 捷报后备本批覆盖5/5；The Odds API主状态仍为额度不足。
"""
    report_path.write_text(report, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-26.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for task in registry["tasks"]:
        if task["key"] == "2026-09-26|16:00|终版分析":
            task.update({
                "status": "completed", "completed_at": NOW,
                "completion_status": "completed_ready_strategy_zero_formal_nowscore_available",
                "artifact": rel(audit_path), "report": rel(report_path),
                "production_plan_rows": 0, "production_ledger_write_performed": False,
                "fixed_odds_shadow_plan_id": FIXED_ID,
            })
    registry["updated_at"] = NOW
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_final_002_006_zero_formal",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-26 14:30终版批次002-006",
        "last_completed_at": NOW,
        "last_stage_status": "completed_002_006_ready_strategy_zero_formal_nowscore_available",
        "last_stage_artifact": rel(report_path),
        "next_required_stage": "2026-09-26 17:00终版分析007",
        "next_required_at": "2026-09-26T17:00:00+08:00",
        "next_dynamic_task_key": "2026-09-26|18:30|终版分析",
        "next_dynamic_task_at": "2026-09-26T17:00:00+08:00",
        "inner_outer_alignment_status": "2026-09-26_1510_primary_quota_insufficient_nowscore_batch_mapped5_of5",  # pragma: allowlist secret - non-secret status or character set
    })
    state["final_20260926_002_006"] = {
        "status": "completed", "completed_at": NOW, "scope": "002-006",
        "formal_strategy_executed": True, "formal_plan_count": 0,
        "formal_reason": audit["formal_plan_reason"], "shadow_scheme_count": len(audit.get("shadow_schemes", [])),
        "fixed_odds_shadow_plan_id": FIXED_ID,
        "external_odds": "the_odds_quota_insufficient_nowscore_mapped5_of5",
        "production_ledger_write_performed": False, "report": rel(report_path),
        "review_due_at": "2026-09-27T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-26",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "scope": "002-006", "formal_rows": 0, "fixed_shadow_added": fixed_added}, ensure_ascii=False))


if __name__ == "__main__":
    main()
