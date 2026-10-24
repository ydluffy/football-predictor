from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-25T12:23:22+08:00"


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def main() -> None:
    report_path = ROOT / "artifacts/betting/sporttery_final_analysis_2026-09-25_1223_001-002.md"
    audit_path = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-25_1223_001-002.json"
    strategy_path = ROOT / "artifacts/data/sporttery_final_strategy_2026-09-25_1223_001-002_audit.json"
    orchestration_path = ROOT / "artifacts/data/sporttery_final_orchestration_2026-09-25_1223_001-002.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    orchestration = json.loads(orchestration_path.read_text(encoding="utf-8"))
    assert strategy["production_plan_rows"] == 0 and orchestration["ok"] is True

    reason = (
        "production strategy executed with zero eligible rows: 002 lacks complete SPF/RQSPF coverage; "
        "the two-match batch has no model-backed formal combination; not blocked by authorization"
    )
    audit.update(
        {
            "formal_plan_reason": reason,
            "production_strategy_executed": True,
            "production_strategy_audit": rel(strategy_path),
            "production_plan_rows": 0,
            "production_ledger_write_performed": False,
            "production_ledger_write_reason": reason,
            "orchestration_validation": orchestration,
            "external_odds": {
                "primary_source": "the_odds_api",
                "primary_status": "quota_insufficient",
                "effective_source": "nowscore",
                "effective_status": "available_via_nowscore",
                "captured_at": "2026-09-25T12:26:55+08:00",
                "mapped_matches": 2,
                "per_match": {
                    "001": "Uzbekistan U23 -1.0 at 10 books (avg 2.00/1.77), four books -0.75; aligns with favorite but warns against a clean -1 cover",
                    "002": "China women -3.0 at 10 books (avg 1.87/1.89); aligns with Sporttery -3 and leaves the exact three-goal margin live",
                },
                "production_model_feature_ready": False,
            },
            "baseline_note": "10:00 preopen was missed; the 12:23 live confirm is the first legal same-day snapshot, so no fabricated earlier movement is reported",
        }
    )
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = report_path.read_text(encoding="utf-8")
    report = report.replace(
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。",
        "已按每组100元规则执行正式策略并通过编排校验。稳健正式0组、价值正式0组、正式台账新增0行：002未开SPF且玩法覆盖不完整，本批也没有模型支持的合格正式组合；不是授权闸门拦截。",
    )
    report += """

## 数据时效与内外盘

- 今日10:00预扫描漏跑，未倒填；12:23在售确认是首个合法同日快照，因此不伪造早盘到终版变化。
- The Odds API余额不足，捷报后备13/13映射。001主流乌兹别克亚-1（10家公司，主/客均价2.00/1.77），另4家-0.75；与体彩-1方向一致，但受让侧低价提示不宜把穿盘当稳胆。
- 002主流中国女-3（10家公司，均价1.87/1.89），与体彩-3一致；三球差仍可能落在让平，不宜只押让胜。

## 冻结状态

- 正式方案0组，正式投入0元；门禁原因是玩法覆盖和模型支持，不是授权问题。
- 固定赔率影子无合格组合，未写入固定赔率台账。
- 邪修影子：001(-1)让负@2.29，虚拟本金2元，单关资格未核验。
- 其余影子方案：让球组合20元、总进球复式8元、比分复式8元；与正式台账分开复盘。
"""
    report_path.write_text(report, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-25.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for task in registry["tasks"]:
        if task["key"] == "2026-09-25|13:00-14:00|终版分析":
            task.update(
                {
                    "status": "completed",
                    "completed_at": NOW,
                    "completion_status": "completed_ready_strategy_zero_formal_nowscore_available",
                    "artifact": rel(audit_path),
                    "report": rel(report_path),
                    "production_plan_rows": 0,
                    "production_ledger_write_performed": False,
                }
            )
    registry["updated_at"] = NOW
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    yesterday_registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-24.json"
    yesterday = json.loads(yesterday_registry_path.read_text(encoding="utf-8"))
    missed = None
    for task in yesterday["tasks"]:
        if task["key"] == "2026-09-24|02:45|终版分析" and task["status"] != "completed":
            task.update(
                {
                    "status": "expired_missed",
                    "closed_at": NOW,
                    "completion_status": "missed_heartbeat_no_legal_post_lock_backfill",
                    "production_ledger_write_performed": False,
                }
            )
            missed = task
    yesterday["updated_at"] = NOW
    yesterday_registry_path.write_text(json.dumps(yesterday, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    missed_path = ROOT / "artifacts/data/missed_final_audit_2026-09-24_004-008.json"
    missed_path.write_text(
        json.dumps(
            {
                "sales_day": "2026-09-24",
                "scope": "004-008",
                "status": "expired_missed",
                "scheduled_at": "2026-09-24T21:00:00+08:00",
                "hard_lock": "2026-09-24T21:45:00+08:00",
                "detected_at": NOW,
                "cause": "no heartbeat execution completed the registered batch before hard lock",
                "post_lock_policy": "results only; no retrospective prediction, formal plan, fixed shadow or contrarian write",
                "task": missed,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(
        {
            "last_heartbeat_at": NOW,
            "last_completed_stage": "2026-09-25 13:00-14:00终版批次001-002",
            "last_completed_at": NOW,
            "last_stage_status": "completed_001_002_ready_strategy_zero_formal_nowscore_available",
            "last_stage_artifact": rel(report_path),
            "next_dynamic_task_key": "2026-09-25|18:00-18:30|终版分析",
            "next_dynamic_task_at": "2026-09-25T16:30:00+08:00",
            "next_required_stage": "2026-09-25 13:00复盘2026-09-24销售日",
            "next_required_at": "2026-09-25T13:00:00+08:00",
        }
    )
    state["final_20260925_001_002"] = {
        "status": "completed",
        "completed_at": NOW,
        "scope": "001-002",
        "formal_strategy_executed": True,
        "formal_plan_count": 0,
        "shadow_scheme_count": 4,
        "external_odds": "the_odds_quota_insufficient_nowscore_mapped2_of2",
        "production_ledger_write_performed": False,
        "report": rel(report_path),
        "review_due_at": "2026-09-26T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-25",
    }
    state["missed_final_20260924_004_008"] = {
        "status": "expired_missed",
        "detected_at": NOW,
        "artifact": rel(missed_path),
        "post_lock_backfill": False,
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "scope": "001-002", "formal": 0, "missed_yesterday": "004-008"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
