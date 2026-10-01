from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_AT = "2026-09-23T21:07:11+08:00"


def main() -> None:
    report_path = ROOT / "artifacts/betting/sporttery_final_analysis_2026-09-23_2107_003.md"
    audit_path = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-23_2107_003.json"
    strategy_path = ROOT / "artifacts/data/sporttery_final_strategy_2026-09-23_2107_003_audit.json"
    orchestration_path = ROOT / "artifacts/data/sporttery_final_orchestration_2026-09-23_2107_003.json"

    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    orchestration = json.loads(orchestration_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert strategy["production_plan_rows"] == 0
    assert orchestration["ok"] is True

    audit.update(
        {
            "formal_plans": [],
            "formal_plan_reason": "production_strategy_executed_with_zero_eligible_rows; one-match batch cannot form an eligible multi-match formal combination and single-bet qualification is unverified",
            "production_strategy_audit": str(strategy_path.relative_to(ROOT)).replace("\\", "/"),
            "production_strategy_executed": True,
            "production_plan_rows": 0,
            "production_ledger_write_performed": False,
            "production_ledger_write_reason": "formal strategy produced zero rows; not blocked by authorization",
            "orchestration_validation": orchestration,
            "fixed_odds_shadow": {"status": "no_action", "reason": "single-match batch cannot form a 6.00-10.00 combination"},
            "additional_shadow_schemes": [
                {"id": "SPF_HEDGE", "selection": "003主胜@1.65/平@3.70", "bets": 2, "stake": 4.0, "payout_range": "3.30-7.40", "formal": False},
                {"id": "RQ_MIDDLE", "selection": "003(-1)让平@3.40", "bets": 1, "stake": 2.0, "payout_range": "6.80", "formal": False},
                {"id": "GOALS_HEDGE", "selection": "003总进球3@3.15/4@4.25", "bets": 2, "stake": 4.0, "payout_range": "6.30-8.50", "formal": False},
                {"id": "SCORE_HEDGE", "selection": "003比分2:1@6.25/1:1@7.30", "bets": 2, "stake": 4.0, "payout_range": "12.50-14.60", "formal": False},
            ],
            "external_odds": {
                "primary_source": "the_odds_api",
                "primary_status": "no_routed_sports",
                "effective_source": "nowscore",
                "effective_status": "available_via_nowscore",
                "mapped_matches": 1,
                "nowscore_match_id": "2908516",
                "captured_at": "2026-09-23T21:11:11.825891+08:00",
                "current_asian_rows": 14,
                "line_distribution": {"-0.75": 13, "-0.5": 1},
                "comparison": "Nowscore consensus -0.75 is shallower than Sporttery -1; it supports Seattle as favorite but emphasizes one-goal-margin or non-cover risk",
                "production_model_feature_ready": False,
            },
        }
    )
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    text = report_path.read_text(encoding="utf-8")
    text = text.replace(
        "外盘：鉴权探针HTTP 200，密钥有效，但当前仅余1 credit，不足以执行路由后的多市场刷新；本批0映射并排除。没有统一可核验的首发、伤停、xG或旅行负荷。",
        "外盘：The Odds API因赛事无路由而0映射；Nowscore后备将003唯一映射至2908516。14条当前亚洲盘中13条为西雅图-0.75、1条为-0.5，整体浅于体彩-1；支持西雅图占优，但更强调一球小胜或不穿盘。后备仅作盘口参照，尚未进入生产模型特征。",
    )
    text = text.replace(
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。",
        "已按每组100元规则执行正式策略并通过编排校验。正式稳健0组、正式价值0组、正式台账新增0行：本批仅1场，不能组成合格多场正式组合，单关资格也未核验；不是授权闸门拦截。",
    )
    text += """

## 补充影子方案（均不入正式台账）

|方案|完整选择|注数/倍数|虚拟本金|理论返奖|用途|
|---|---|---:|---:|---:|---|
|胜平防守|003主胜@1.65 / 平@3.70|2注×1倍|4元|3.30—7.40元|覆盖主队取胜与平局|
|一球差观察|003(-1)让平@3.40|1注×1倍|2元|6.80元|外盘-0.75支持一球小胜结构|
|进球结构|003总进球3@3.15 / 4@4.25|2注×1倍|4元|6.30—8.50元|对应2:1、3:1等路径|
|比分窄选|003比分2:1@6.25 / 1:1@7.30|2注×1倍|4元|12.50—14.60元|高方差，仅作观察|

邪修影子为003(-1)让负@1.93、虚拟本金2元，须与上述方案和正式台账分开复盘；不倍投、不追损。
"""
    report_path.write_text(text, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-23.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for task in registry["tasks"]:
        if task["key"] == "2026-09-23|09:30|终版分析":
            task.update(
                {
                    "status": "completed",
                    "completed_at": ANALYSIS_AT,
                    "completion_status": "completed_ready_strategy_zero_formal_single_match_nowscore_available",
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
            "last_completed_stage": "2026-09-23 09:30终版批次003",
            "last_completed_at": ANALYSIS_AT,
            "last_stage_status": "completed_003_ready_strategy_zero_formal_single_match_nowscore_available",
            "last_stage_artifact": str(report_path.relative_to(ROOT)).replace("\\", "/"),
            "inner_outer_alignment_status": "2026-09-23_2107_primary_no_routed_sports_nowscore_mapped_1_of_1_research_available_production_feature_not_ready",
            "next_dynamic_task_key": None,
            "next_dynamic_task_at": None,
            "next_required_stage": "2026-09-24 10:00开售前预扫描；13:00复盘2026-09-23销售日",
            "next_required_at": "2026-09-24T10:00:00+08:00",
        }
    )
    state["final_20260923_003"] = {
        "status": "completed",
        "completed_at": ANALYSIS_AT,
        "scope": "003",
        "official_captured_at": ANALYSIS_AT,
        "gate": "READY_FOR_FINAL_ANALYSIS",
        "formal_strategy_executed": True,
        "formal_plan_count": 0,
        "formal_reason": "single_match_batch_no_verified_single_bet_eligibility",
        "shadow_scheme_count": 5,
        "external_odds": "the_odds_no_route_nowscore_mapped1_of1_consensus_minus0_75",
        "production_ledger_write_performed": False,
        "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "review_due_at": "2026-09-24T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-23",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "match": "003", "production_plan_rows": 0, "external": "available_via_nowscore"}, ensure_ascii=True))


if __name__ == "__main__":
    main()
