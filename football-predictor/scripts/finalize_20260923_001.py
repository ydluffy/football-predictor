from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-23"
ANALYSIS_AT = "2026-09-23T13:06:03+08:00"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    report_path = ROOT / "artifacts/betting/sporttery_final_analysis_2026-09-23_1306_001.md"
    audit_path = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-23_1306_001.json"
    strategy_path = ROOT / "artifacts/data/sporttery_final_strategy_2026-09-23_1306_001_audit.json"
    orchestration_path = ROOT / "artifacts/data/sporttery_final_orchestration_2026-09-23_1306_001.json"
    nowscore_dir = ROOT / "data/external/nowscore/snapshots/2026-09-23_20260923T030828532165Z"

    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    orchestration = json.loads(orchestration_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert strategy["production_plan_rows"] == 0
    assert orchestration["ok"] is True

    quotes = [r for r in read_rows(nowscore_dir / "quotes.csv") if r.get("match_id") == f"{DAY}|001"]
    asian = [
        r for r in quotes
        if r.get("market") == "asian_handicap" and r.get("stage") == "current"
        and r.get("home_handicap") and r.get("home_odds") and r.get("away_odds")
    ]
    lines = Counter(r["home_handicap"] for r in asian)
    line_summary = "、".join(f"{line}球×{count}" for line, count in lines.most_common())

    audit.update(
        {
            "formal_plans": [],
            "formal_plan_reason": "production_strategy_executed_with_zero_eligible_rows; favorite probability 0.4788 below 0.52 and no model-backed handicap edge",
            "production_strategy_audit": str(strategy_path.relative_to(ROOT)).replace("\\", "/"),
            "production_strategy_executed": True,
            "production_plan_rows": 0,
            "production_ledger_write_performed": False,
            "production_ledger_write_reason": "formal strategy produced zero rows; not blocked by authorization",
            "orchestration_validation": orchestration,
            "fixed_odds_shadow": {"status": "no_action", "reason": "single-match batch cannot form a 6.00-10.00 combination"},
            "external_odds": {
                "primary_source": "the_odds_api",
                "primary_status": "no_routed_sports",
                "effective_source": "nowscore",
                "effective_status": "available_via_nowscore",
                "mapped_matches": 1,
                "nowscore_match_id": "3049659",
                "captured_at": "2026-09-23T03:08:28.532165+00:00",
                "asian_current_rows_001": len(asian),
                "asian_current_line_distribution": dict(lines),
                "production_model_feature_ready": False,
            },
        }
    )
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    text = report_path.read_text(encoding="utf-8")
    old_external = "外盘：鉴权探针HTTP 200，密钥有效，但当前仅余1 credit，不足以执行路由后的多市场刷新；本批0映射并排除。没有统一可核验的首发、伤停、xG或旅行负荷。"
    new_external = (
        "外盘：The Odds API因赛事无路由而0映射；Nowscore后备将001唯一映射至3049659。"
        f"11:08前赛前快照的当前亚洲让球分布为{line_summary}，主流为中国亚-0.5，明显浅于体彩-1；"
        "因此外盘更支持中国亚不败/小胜，而不支持深盘穿盘。该后备仅作盘口参照，尚未进入生产模型特征。"
    )
    text = text.replace(old_external, new_external)
    old_formal = "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。"
    new_formal = (
        "已按每组100元规则执行正式策略并通过编排校验。正式候选0组、正式台账新增0行："
        "主胜市场概率0.4788低于0.52门槛，且无模型支持的让球优势；不是授权闸门拦截。"
    )
    text = text.replace(old_formal, new_formal)
    text += (
        "\n## 正式策略补充\n\n"
        "- 正式稳健方案：0组；正式价值方案：0组；标准本金仍为每组100元。\n"
        "- 影子防冷：001胜平负主胜/平，2注×1倍，虚拟本金4元，返奖区间3.70—6.00元。\n"
        "- 影子博高：001(-1)让平@3.40，1注×1倍，虚拟本金2元，理论返奖6.80元。\n"
        "- 邪修影子：001(-1)让负@1.75，虚拟本金2元；与正式台账隔离。\n"
        "- 固定赔率影子：0组；单场不能形成6.00—10.00组合。\n"
    )
    report_path.write_text(text, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-23.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for task in registry["tasks"]:
        if task["key"] == "2026-09-23|13:30|终版分析":
            task.update(
                {
                    "status": "completed",
                    "completed_at": ANALYSIS_AT,
                    "completion_status": "completed_ready_strategy_zero_formal_nowscore_available",
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
            "last_completed_stage": "2026-09-23 13:30终版批次001",
            "last_completed_at": ANALYSIS_AT,
            "last_stage_status": "completed_001_ready_strategy_zero_formal_nowscore_available",
            "last_stage_artifact": str(report_path.relative_to(ROOT)).replace("\\", "/"),
            "inner_outer_alignment_status": "2026-09-23_1306_primary_no_routed_sports_nowscore_mapped_1_of_1_research_available_production_feature_not_ready",
            "next_dynamic_task_key": None,
            "next_dynamic_task_at": None,
            "next_required_stage": "2026-09-23 13:00复盘2026-09-22销售日",
            "next_required_at": "2026-09-23T13:00:00+08:00",
        }
    )
    state["final_20260923_001"] = {
        "status": "completed",
        "completed_at": ANALYSIS_AT,
        "scope": "001",
        "official_captured_at": ANALYSIS_AT,
        "gate": "READY_FOR_FINAL_ANALYSIS",
        "formal_strategy_executed": True,
        "formal_plan_count": 0,
        "formal_reason": "favorite_probability_below_0.52_and_no_model_backed_handicap",
        "shadow_scheme_count": 3,
        "external_odds": "the_odds_no_route_nowscore_mapped1_of1",
        "production_ledger_write_performed": False,
        "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "review_due_at": "2026-09-24T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-23",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"status": "completed", "match": "001 中国亚 vs 阿联酋亚", "production_plan_rows": 0, "external": "available_via_nowscore"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
