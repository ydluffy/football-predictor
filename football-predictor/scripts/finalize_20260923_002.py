from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_AT = "2026-09-23T17:05:07+08:00"


def main() -> None:
    report_path = ROOT / "artifacts/betting/sporttery_final_analysis_2026-09-23_1705_002.md"
    audit_path = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-23_1705_002.json"
    strategy_path = ROOT / "artifacts/data/sporttery_final_strategy_2026-09-23_1705_002_audit.json"
    orchestration_path = ROOT / "artifacts/data/sporttery_final_orchestration_2026-09-23_1705_002.json"

    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    orchestration = json.loads(orchestration_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert strategy["production_plan_rows"] == 0
    assert orchestration["ok"] is True

    audit.update(
        {
            "formal_plans": [],
            "formal_plan_reason": "production_strategy_executed_with_zero_eligible_rows; official SPF unavailable and the one-match batch has incomplete SPF/RQSPF coverage",
            "production_strategy_audit": str(strategy_path.relative_to(ROOT)).replace("\\", "/"),
            "production_strategy_executed": True,
            "production_plan_rows": 0,
            "production_ledger_write_performed": False,
            "production_ledger_write_reason": "formal strategy produced zero rows because official market coverage is incomplete; not blocked by authorization",
            "orchestration_validation": orchestration,
            "fixed_odds_shadow": {"status": "no_action", "reason": "single-match batch cannot form a 6.00-10.00 combination"},
            "additional_shadow_schemes": [
                {"id": "RQ_HEDGE", "selection": "002(-2)让胜@1.58/让平@4.35", "bets": 2, "stake": 4.0, "payout_range": "3.16-8.70", "formal": False},
                {"id": "GOALS_HEDGE", "selection": "002总进球3@4.25/4@4.30", "bets": 2, "stake": 4.0, "payout_range": "8.50-8.60", "formal": False},
                {"id": "SCORE_HEDGE", "selection": "002比分3:0@6.00/2:0@7.00", "bets": 2, "stake": 4.0, "payout_range": "12.00-14.00", "formal": False},
            ],
            "external_odds": {
                "primary_source": "the_odds_api",
                "primary_status": "no_routed_sports",
                "effective_source": "nowscore",
                "effective_status": "available_via_nowscore",
                "mapped_matches": 1,
                "nowscore_match_id": "3049653",
                "captured_at": "2026-09-23T17:11:25.439039+08:00",
                "current_asian_line": "-3.0",
                "current_home_odds": 1.90,
                "current_away_odds": 1.82,
                "comparison": "Nowscore -3 is one goal deeper than Sporttery -2; supports a strong Japan win but the lower away-side price warns that clearing three goals is not low risk",
                "production_model_feature_ready": False,
            },
        }
    )
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    text = report_path.read_text(encoding="utf-8")
    text = text.replace(
        "外盘：鉴权探针HTTP 200，密钥有效，但当前仅余1 credit，不足以执行路由后的多市场刷新；本批0映射并排除。没有统一可核验的首发、伤停、xG或旅行负荷。",
        "外盘：The Odds API因赛事无路由而0映射；Nowscore后备将002唯一映射至3049653。赛前当前亚洲盘为日本亚-3，主队1.90、客队1.82；比体彩-2深一球，支持日本大胜，但受让侧价格更低，穿三球仍有阻力。后备仅作盘口参照，尚未进入生产模型特征。",
    )
    text = text.replace(
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。",
        "已按每组100元规则执行正式策略并通过编排校验。正式稳健0组、正式价值0组、正式台账新增0行：体彩SPF未开且单场SPF/RQSPF覆盖不完整，策略明确拒绝生成生产候选；不是授权闸门拦截。",
    )
    text += """

## 补充影子方案（均不入正式台账）

|方案|完整选择|注数/倍数|虚拟本金|理论返奖|用途|
|---|---|---:|---:|---:|---|
|让球防守|002(-2)让胜@1.58 / 让平@4.35|2注×1倍|4元|3.16—8.70元|覆盖赢3球以上及恰好赢2球|
|进球结构|002总进球3@4.25 / 4@4.30|2注×1倍|4元|8.50—8.60元|对应3:0、2:1、4球附近|
|比分窄选|002比分3:0@6.00 / 2:0@7.00|2注×1倍|4元|12.00—14.00元|高方差，仅作观察|

上述方案与邪修002(-2)让胜@1.58分开统计；单关资格未核验，不倍投、不追损。
"""
    report_path.write_text(text, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-23.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for task in registry["tasks"]:
        if task["key"] == "2026-09-23|18:30|终版分析":
            task.update(
                {
                    "status": "completed",
                    "completed_at": ANALYSIS_AT,
                    "completion_status": "completed_ready_strategy_zero_formal_incomplete_spf_nowscore_available",
                    "artifact": str(audit_path.relative_to(ROOT)).replace("\\", "/"),
                    "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
                    "production_plan_rows": 0,
                    "production_ledger_write_performed": False,
                }
            )
    registry["updated_at"] = ANALYSIS_AT
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(
        {
            "last_heartbeat_at": ANALYSIS_AT,
            "last_completed_stage": "2026-09-23 18:30终版批次002",
            "last_completed_at": ANALYSIS_AT,
            "last_stage_status": "completed_002_ready_strategy_zero_formal_incomplete_spf_nowscore_available",
            "last_stage_artifact": str(report_path.relative_to(ROOT)).replace("\\", "/"),
            "inner_outer_alignment_status": "2026-09-23_1705_primary_no_routed_sports_nowscore_mapped_1_of_1_research_available_production_feature_not_ready",
            "next_dynamic_task_key": "2026-09-23|09:30|终版分析",
            "next_dynamic_task_at": "2026-09-23T21:00:00+08:00",
            "next_required_stage": "2026-09-23 21:00终版分析003 西雅图 vs 盐湖城",
            "next_required_at": "2026-09-23T21:00:00+08:00",
        }
    )
    state["final_20260923_002"] = {
        "status": "completed",
        "completed_at": ANALYSIS_AT,
        "scope": "002",
        "official_captured_at": ANALYSIS_AT,
        "gate": "READY_FOR_FINAL_ANALYSIS",
        "formal_strategy_executed": True,
        "formal_plan_count": 0,
        "formal_reason": "incomplete_spf_or_rqspf_market",
        "shadow_scheme_count": 4,
        "external_odds": "the_odds_no_route_nowscore_mapped1_of1_current_asian_minus3",
        "production_ledger_write_performed": False,
        "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "review_due_at": "2026-09-24T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-23",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "match": "002", "production_plan_rows": 0, "external": "available_via_nowscore"}, ensure_ascii=True))


if __name__ == "__main__":
    main()
