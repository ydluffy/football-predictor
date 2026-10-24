from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-30T17:00:55+08:00"
REPORT = "artifacts/betting/sporttery_final_analysis_2026-09-30_1700_002.md"
AUDIT = "artifacts/data/sporttery_final_analysis_2026-09-30_1700_002.json"
STRATEGY = "artifacts/data/production_strategy_2026-09-30_1700_002.json"
ORCHESTRATION = "artifacts/data/final_orchestration_validation_2026-09-30_1700_002.json"


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def main() -> None:
    audit = load(AUDIT)
    strategy = load(STRATEGY)
    orchestration = load(ORCHESTRATION)
    if strategy["production_plan_rows"] != 0 or not orchestration["ok"]:
        raise ValueError("final strategy artifacts are inconsistent")
    reason = (
        "002 passes the formal favorite screen at probability 0.6106 and odds 1.45, but this batch contains only one "
        "match and the controlled handicap model is blocked outside its training domain; no legal two-leg formal "
        "safe/value plan exists"
    )
    audit.update({
        "formal_plans": [],
        "formal_plan_reason": reason,
        "production_strategy_audit": STRATEGY,
        "production_strategy_executed": True,
        "production_plan_rows": 0,
        "production_ledger_write_performed": False,
        "orchestration_validation": orchestration,
        "fixed_odds_shadow": {
            "status": "no_action",
            "reason": "single-match batch cannot form a 6-to-10 odds combination",
        },
        "external_odds": {
            "primary_source": "the_odds_api",
            "primary_status": "no_routed_sports",
            "effective_source": "nowscore",
            "effective_status": "available_via_nowscore",
            "mapped_matches_batch": 1,
            "research_eligible_rows": 14,
            "per_match": {
                "002": "14 eligible books all quote Uzbekistan U23 +1; home decimal 1.78-1.91, away 1.83-1.99"
            },
            "production_model_feature_ready": False,
        },
    })
    (ROOT / AUDIT).write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_path = ROOT / REPORT
    report = report_path.read_text(encoding="utf-8")
    report = report.replace(
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。",
        "已按每组100元规则执行正式策略并通过编排校验。正式稳健0组、价值0组、正式台账新增0行：002客胜概率0.6106、赔率1.45通过热门筛选，但本批只有一个合格腿，且让球模型因超出训练域被阻断，无法组成合法二串一。不是授权闸门拦截。",
    )
    report += """

## 内外盘终版对照

- The Odds API无亚运男足赛事路由，未发送付费赔率请求。
- 捷报后备002唯一映射成功，14家公司当前亚洲盘全部为乌兹别亚+1；主队水位折算十进制1.78—1.91，客队1.83—1.99。盘口与体彩+1一致，只作研究对照，未升级为生产模型特征。
- 体彩11:05→17:00：日本亚客胜1.58→1.45，乌兹别亚主胜4.85→6.00、平3.45→3.66；客胜继续受压。+1让胜2.05→2.37、让平3.30→3.07、让负2.95→2.62，胜负与穿盘信号分裂，需防日本亚仅胜一球。

## 完整方案与金额（严格分层）

- 正式方案：0组，正式投入0元；单场批次无法组成合法二串一。
- 固定赔率影子：无6—10倍合格组合，未写固定赔率影子台账。
- 防冷影子：002客胜@1.45／平@3.66双选，各2元，虚拟总投入4元；返奖区间2.90—7.32元。
- 博高影子：002(+1)让平@3.07，虚拟投入2元；预计返奖6.14元。
- 邪修影子：002乌兹别亚(+1)让胜@2.37，虚拟投入2元；单关资格未核验，不倍投、不追损，与正式台账分开。
"""
    report_path.write_text(report, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-30.json"
    registry = load("artifacts/data/sporttery_task_registry_2026-09-30.json")
    updated = 0
    for task in registry["tasks"]:
        if task["key"] == "2026-09-30|18:30|终版分析":
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
        raise ValueError("002 registry task not found")
    registry["updated_at"] = NOW
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = load("artifacts/data/football_automation_controller_state.json")
    state.update({
        "status": "completed_final_002_zero_formal_nowscore_available",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-30 17:00终版批次002",
        "last_completed_at": NOW,
        "last_stage_status": "completed_002_ready_strategy_zero_formal_nowscore_available",
        "last_stage_artifact": REPORT,
        "next_dynamic_task_key": None,
        "next_dynamic_task_at": None,
        "next_required_stage": "2026-10-01 10:00开售前预扫描",
        "next_required_at": "2026-10-01T10:00:00+08:00",
        "pending_reschedule": True,
        "pending_reschedule_reason": "current sales-day queue completed; controller must be moved to next-day 10:00 anchor and read back",
    })
    state["final_20260930_002"] = {
        "status": "completed",
        "completed_at": NOW,
        "scope": "002",
        "official_captured_at": NOW,
        "gate": "READY_FOR_FINAL_ANALYSIS",
        "formal_strategy_executed": True,
        "formal_plan_count": 0,
        "formal_reason": reason,
        "fixed_odds_shadow_count": 0,
        "observation_scheme_count": 3,
        "external_odds": "the_odds_no_routed_sports_nowscore_mapped1_of1_research_only",
        "production_ledger_write_performed": False,
        "production_ledger_sha256": hashlib.sha256((ROOT / "data/manual/betting_plan_ledger.csv").read_bytes()).hexdigest(),
        "report": REPORT,
        "review_due_at": "2026-10-01T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-30",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "scope": "002", "formal": 0, "next": "2026-10-01T10:00:00+08:00"}))


if __name__ == "__main__":
    main()
