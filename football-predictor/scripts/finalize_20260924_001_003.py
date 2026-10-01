from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_AT = "2026-09-24T17:06:50+08:00"
SCOPE = "001-003"


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def main() -> None:
    report_path = ROOT / "artifacts/betting/sporttery_final_analysis_2026-09-24_1706_001-003.md"
    audit_path = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-24_1706_001-003.json"
    strategy_path = ROOT / "artifacts/data/sporttery_final_strategy_2026-09-24_1706_001-003_audit.json"
    orchestration_path = ROOT / "artifacts/data/sporttery_final_orchestration_2026-09-24_1706_001-003.json"
    fixed_path = ROOT / "artifacts/data/sporttery_fixed_odds_shadow_2026-09-24_1706_001-003.json"

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    orchestration = json.loads(orchestration_path.read_text(encoding="utf-8"))
    fixed = json.loads(fixed_path.read_text(encoding="utf-8"))
    assert strategy["production_plan_rows"] == 0
    assert orchestration["ok"] is True
    assert fixed["status"] == "recorded"

    formal_reason = (
        "production_strategy_executed_with_zero_eligible_rows; 002 favorite probability 0.4342 "
        "is below 0.52 and odds 2.04 exceed 1.85 with no model-backed handicap; "
        "003 has incomplete SPF/RQSPF coverage; no authorization gate blocked writing"
    )
    audit.update(
        {
            "formal_plans": [],
            "formal_plan_reason": formal_reason,
            "production_strategy_audit": rel(strategy_path),
            "production_strategy_executed": True,
            "production_plan_rows": 0,
            "production_ledger_write_performed": False,
            "production_ledger_write_reason": formal_reason,
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
                "estimated_route_cost": 12,
                "effective_source": "nowscore",
                "effective_status": "available_via_nowscore",
                "captured_at": "2026-09-24T17:10:10+08:00",
                "mapped_matches": 3,
                "research_eligible_rows_all_8_matches": 95,
                "per_match": {
                    "001": {
                        "nowscore_match_id": "3092213",
                        "asian_consensus": "Japan -0.75 (13 books; avg 1.88/1.91), one -0.5",
                        "comparison": "shallower than Sporttery -1; supports Japan favorite but strengthens one-goal/non-cover protection",
                    },
                    "002": {
                        "nowscore_match_id": "3092214",
                        "asian_consensus": "Korea -0.25 (13 books; avg 1.89/1.90), one level ball",
                        "comparison": "shallower than Sporttery -1; supports only a narrow home edge and aligns with -1 handicap loss protection",
                    },
                    "003": {
                        "nowscore_match_id": "3092344",
                        "asian_consensus": "mapped but deep Asian line quotes were not safely normalized",
                        "comparison": "external line excluded from directional inference; official Sporttery -4 remains the baseline",
                    },
                },
                "production_model_feature_ready": False,
            },
        }
    )
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = report_path.read_text(encoding="utf-8")
    report = report.replace(
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。",
        "已按每组100元规则运行正式策略并通过编排校验。稳健正式0组、价值正式0组、正式台账新增0行：002市场概率0.4342低于0.52、主胜2.04高于1.85且无模型让球支持；003未开SPF、玩法覆盖不完整。不是授权闸门拦截。",
    )
    report += """

## 内外盘终版对照

- 主来源 The Odds API：余额1，预计本批路由成本12，因此状态为 `quota_insufficient`，未发出必然失败的付费请求。
- 捷报后备：8/8场唯一映射，本次共95条赛前研究可用报价；001、002亚洲盘可安全使用，003深盘报价未能安全标准化，按体彩基线降级。
- 001 日本 vs 乌拉圭：捷报主流日本-0.75（13家公司，主/客均价1.88/1.91），浅于体彩-1。主胜方向一致，但一球小胜、不穿盘风险上升，因此让负是主要保护。
- 002 韩国 vs 厄瓜多尔：捷报主流韩国-0.25（13家公司，均价1.89/1.90），明显浅于体彩-1。只支持韩国轻微优势，不支持深穿；让负为让球主方向。
- 003 中国 vs 马尔代夫：赛事映射成功，但深盘亚洲报价未通过安全标准化；不拿缺失数据推断盘口，只使用体彩-4及四玩法结构。

## 正式与影子冻结状态

- 正式稳健/价值：0组，每组100元规则已实际执行；正式投入0元。原因是概率、赔率、模型支持与玩法覆盖门禁，不是授权问题。
- 固定赔率影子：已独立冻结1组，2元虚拟本金，组合为001(-1)让负@2.08 + 002主胜@2.04 + 003(-4)让负@2.03，组合赔率8.6137。
- 邪修影子：003(-4)让负@2.03，2元虚拟本金；只作市场异象观察，单关资格未核验，不计正式台账、不倍投追损。
- 其余7组逐场/复式观察方案保留在上表，均不进入正式台账，明日独立复盘。
"""
    report_path.write_text(report, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-24.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for task in registry["tasks"]:
        if task["key"] == "2026-09-24|18:05-19:35|终版分析":
            task.update(
                {
                    "status": "completed",
                    "completed_at": ANALYSIS_AT,
                    "completion_status": "completed_ready_strategy_zero_formal_fixed_shadow_recorded_nowscore_available",
                    "artifact": rel(audit_path),
                    "report": rel(report_path),
                    "production_plan_rows": 0,
                    "production_ledger_write_performed": False,
                    "fixed_odds_shadow_rows": 1,
                }
            )
    registry["updated_at"] = ANALYSIS_AT
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(
        {
            "last_heartbeat_at": ANALYSIS_AT,
            "last_completed_stage": "2026-09-24 18:05-19:35终版批次001-003",
            "last_completed_at": ANALYSIS_AT,
            "last_stage_status": "completed_001_003_ready_strategy_zero_formal_fixed_shadow_recorded_nowscore_available",
            "last_stage_artifact": rel(report_path),
            "inner_outer_alignment_status": "2026-09-24_1706_primary_quota_insufficient_nowscore_mapped3_of3_001_002_asian_safe_003_deep_line_excluded",
            "next_dynamic_task_key": "2026-09-24|02:45|终版分析",
            "next_dynamic_task_at": "2026-09-24T21:00:00+08:00",
            "next_required_stage": "2026-09-24 21:00终版分析004-008",
            "next_required_at": "2026-09-24T21:00:00+08:00",
        }
    )
    state["final_20260924_001_003"] = {
        "status": "completed",
        "completed_at": ANALYSIS_AT,
        "scope": SCOPE,
        "official_captured_at": ANALYSIS_AT,
        "gate": "READY_FOR_FINAL_ANALYSIS",
        "formal_strategy_executed": True,
        "formal_plan_count": 0,
        "formal_reason": formal_reason,
        "fixed_odds_shadow_count": 1,
        "observation_scheme_count": 9,
        "external_odds": "the_odds_quota_insufficient_nowscore_mapped3_of3",
        "production_ledger_write_performed": False,
        "report": rel(report_path),
        "review_due_at": "2026-09-25T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-24",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "scope": SCOPE, "production_plan_rows": 0, "fixed_shadow_rows": 1, "next": "2026-09-24T21:00:00+08:00"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
