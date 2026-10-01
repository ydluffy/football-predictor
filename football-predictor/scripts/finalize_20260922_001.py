from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-22"
ANALYSIS_AT = "2026-09-22T16:13:00+08:00"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    report_path = ROOT / "artifacts/betting/sporttery_final_analysis_2026-09-22_1613_001.md"
    audit_path = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-22_1613_001.json"
    strategy_path = ROOT / "artifacts/data/sporttery_final_strategy_2026-09-22_1606_001_audit.json"
    orchestration_path = ROOT / "artifacts/data/sporttery_final_orchestration_2026-09-22_1606_001.json"
    nowscore_dir = ROOT / "data/external/nowscore/snapshots/2026-09-22_20260922T081224503595Z"

    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    orchestration = json.loads(orchestration_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert strategy["production_plan_rows"] == 0
    assert orchestration["ok"] is True

    quotes = [row for row in rows(nowscore_dir / "quotes.csv") if row.get("match_id") == f"{DAY}|001"]
    asian_current = [
        row for row in quotes
        if row.get("market") == "asian_handicap"
        and row.get("stage") == "current"
        and row.get("home_handicap")
        and row.get("home_odds")
        and row.get("away_odds")
    ]
    line_counts = Counter(row["home_handicap"] for row in asian_current)
    line_summary = "、".join(f"{line}球×{count}" for line, count in line_counts.most_common())
    h2h = [row for row in quotes if row.get("market") == "h2h" and row.get("stage") == "current" and row.get("home_odds")]
    totals = [row for row in quotes if row.get("market") == "totals" and row.get("stage") == "current" and row.get("total_line_raw")]

    audit.update(
        {
            "formal_plans": [],
            "formal_plan_reason": "production_strategy_executed_with_zero_eligible_rows; one-match batch has no verified single-bet eligibility and no model-backed handicap edge",
            "production_strategy_audit": str(strategy_path.relative_to(ROOT)).replace("\\", "/"),
            "production_strategy_executed": True,
            "production_plan_rows": 0,
            "production_ledger_write_performed": False,
            "production_ledger_write_reason": "no eligible formal rows; not blocked by authorization",
            "orchestration_validation": orchestration,
            "fixed_odds_shadow": {"status": "no_action", "reason": "no 6.00-10.00 eligible combination in one-match batch"},
            "external_odds": {
                "primary_source": "the_odds_api",
                "primary_status": "no_routed_sports",
                "effective_source": "nowscore",
                "effective_status": "available_via_nowscore",
                "mapped_matches": 1,
                "nowscore_match_id": "3049669",
                "captured_at": "2026-09-22T08:12:25.703502+00:00",
                "research_eligible_rows_all_matches": 54,
                "asian_current_rows_001": len(asian_current),
                "asian_current_line_distribution": dict(line_counts),
                "h2h_current_rows_001": len(h2h),
                "totals_current_rows_001": len(totals),
                "production_model_feature_ready": False,
            },
            "early_execution": {
                "heartbeat_at": "2026-09-22T16:06:44+08:00",
                "registered_run_at": "2026-09-22T16:30:00+08:00",
                "reason": "within 35-minute heartbeat safety window with fresh official data available",
            },
        }
    )
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    text = report_path.read_text(encoding="utf-8")
    old_external = "外盘：鉴权探针HTTP 200，密钥有效，但当前仅余1 credit，不足以执行路由后的多市场刷新；本批0映射并排除。没有统一可核验的首发、伤停、xG或旅行负荷。"
    new_external = (
        "外盘：The Odds API主来源因赛事无路由而0映射；已自动启用Nowscore后备，001按场次号、球队与开赛时间唯一映射至3049669。"
        f"赛前合格外盘显示当前亚洲让球分布为{line_summary}；主流-1.25比体彩-1更深，但多数-1.25报价中客队受让价格更低，支持韩国赢球、同时提示穿深盘阻力。"
        "后备数据可作盘口参照，但尚未升级为生产模型特征。"
    )
    text = text.replace(old_external, new_external)
    old_formal = (
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。"
    )
    new_formal = (
        "已执行 `build_multi_play_betting_strategy.py --stake 100` 并通过终版编排校验。正式候选0组、正式台账新增0行：原因不是授权闸门，"
        "而是本批只有1场，未核验该场单关资格，也没有模型支持的让球正期望边；策略生成的防冷与让平脚本均明确标记为影子。标准100元本金规则仍保留，只有正式候选成立时才入账。"
    )
    text = text.replace(old_formal, new_formal)
    supplement = (
        "\n## 正式策略与外盘审计补充\n\n"
        "- 正式策略：已运行；生产候选0组，影子候选2组；编排校验通过。\n"
        "- 影子候选A（防冷）：001胜平负主胜/平，2注、1倍、虚拟本金4元，赔率区间1.29—4.50。\n"
        "- 影子候选B（博高）：001(-1)让平@3.75，1注、1倍、虚拟本金2元。\n"
        "- 邪修影子：001(-1)让胜@1.95，虚拟本金2元；与上述影子分开记录，不进入正式台账。\n"
        "- 固定赔率影子：0组；单场无法组成6.00—10.00的合格组合。\n"
        "- 外盘快照：Nowscore 001当前亚洲盘"
        f"{line_summary}；完整原始报价、映射和审计保存在 `{nowscore_dir.relative_to(ROOT)}`。\n"
        "- 正式台账：没有新增记录；未获本销售日Supabase同步授权。\n"
    )
    if "## 正式策略与外盘审计补充" not in text:
        text += supplement
    report_path.write_text(text, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-22.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for task in registry["tasks"]:
        if task["key"] == "2026-09-22|18:00|终版分析":
            task.update(
                {
                    "status": "completed",
                    "completed_at": ANALYSIS_AT,
                    "completion_status": "completed_ready_strategy_zero_formal_three_shadow_views_nowscore_available",
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
            "last_completed_stage": "2026-09-22 18:00终版批次001",
            "last_completed_at": ANALYSIS_AT,
            "last_stage_status": "completed_001_ready_strategy_zero_formal_nowscore_available_three_shadow_views",
            "last_stage_artifact": str(report_path.relative_to(ROOT)).replace("\\", "/"),
            "inner_outer_alignment_status": "2026-09-22_1613_primary_no_routed_sports_nowscore_mapped_1_of_1_research_available_production_feature_not_ready",
            "next_dynamic_task_key": "2026-09-22|02:00|终版分析",
            "next_dynamic_task_at": "2026-09-22T21:00:00+08:00",
            "next_required_stage": "2026-09-22 21:00终版分析002-004",
            "next_required_at": "2026-09-22T21:00:00+08:00",
        }
    )
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": "completed",
        "match": "001 韩国亚 vs 沙特亚",
        "production_plan_rows": 0,
        "strategy_shadow_rows": strategy["shadow_plan_rows"],
        "contrarian_shadow_rows": len(audit.get("shadow_schemes", [])),
        "external": "available_via_nowscore",
        "report": str(report_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
