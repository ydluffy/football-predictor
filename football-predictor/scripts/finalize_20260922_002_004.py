from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-22"
ANALYSIS_AT = "2026-09-22T21:12:00+08:00"


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    report_path = ROOT / "artifacts/betting/sporttery_final_analysis_2026-09-22_2112_002-004.md"
    audit_path = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-22_2112_002-004.json"
    strategy_path = ROOT / "artifacts/data/sporttery_final_strategy_2026-09-22_2105_002-004_audit.json"
    orchestration_path = ROOT / "artifacts/data/sporttery_final_orchestration_2026-09-22_2105_002-004.json"
    fixed_path = ROOT / "artifacts/data/fixed_odds_shadow_2026-09-22_2112_002-004.json"
    nowscore_dir = ROOT / "data/external/nowscore/snapshots/2026-09-22_20260922T130918166053Z"

    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    orchestration = json.loads(orchestration_path.read_text(encoding="utf-8"))
    fixed = json.loads(fixed_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert strategy["production_plan_rows"] == 0
    assert strategy["shadow_plan_rows"] == 3
    assert orchestration["ok"] is True
    assert fixed["status"] in {"recorded", "duplicate"}

    quotes = csv_rows(nowscore_dir / "quotes.csv")
    alignments = {
        row["match_number"]: row
        for row in csv_rows(nowscore_dir / "alignment.csv")
        if row["match_number"] in {"002", "003", "004"}
    }
    outer: dict[str, dict[str, object]] = {}
    for number in ("002", "003", "004"):
        current = [
            row for row in quotes
            if row.get("match_id") == f"{DAY}|{number}"
            and row.get("market") == "asian_handicap"
            and row.get("stage") == "current"
            and row.get("home_handicap")
            and row.get("home_odds")
            and row.get("away_odds")
        ]
        distribution = Counter(row["home_handicap"] for row in current)
        outer[number] = {
            "nowscore_match_id": alignments[number]["nowscore_match_id"],
            "mapping_status": alignments[number]["mapping_status"],
            "current_asian_rows": len(current),
            "line_distribution": dict(distribution),
        }

    audit.update(
        {
            "formal_plans": [],
            "formal_plan_reason": "strategy_executed; only 002 passed the market favorite screen, while 003 and 004 failed probability/price/model-backed-handicap gates, so no eligible formal parlay was formed",
            "production_strategy_audit": str(strategy_path.relative_to(ROOT)).replace("\\", "/"),
            "production_strategy_executed": True,
            "production_plan_rows": 0,
            "production_ledger_write_performed": False,
            "production_ledger_write_reason": "no eligible formal rows; not blocked by authorization",
            "orchestration_validation": orchestration,
            "fixed_odds_shadow": {
                "status": fixed["status"],
                "plan_id": fixed["plan_id"],
                "selection": fixed["selection"],
                "odds": fixed["odds"],
                "virtual_stake": 2.0,
                "production_ledger_write_performed": False,
            },
            "external_odds": {
                "primary_source": "the_odds_api",
                "primary_status": "no_routed_sports",
                "effective_source": "nowscore",
                "effective_status": "available_via_nowscore",
                "captured_at": "2026-09-22T13:09:18.166053+00:00",
                "mapped_matches": 3,
                "research_eligible_rows_all_three": 40,
                "matches": outer,
                "production_model_feature_ready": False,
            },
        }
    )
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    text = report_path.read_text(encoding="utf-8")
    old_external = "外盘：鉴权探针HTTP 200，密钥有效，但当前仅余1 credit，不足以执行路由后的多市场刷新；本批0映射并排除。没有统一可核验的首发、伤停、xG或旅行负荷。"
    line_text = "；".join(
        f"{number}=" + "/".join(f"{line}×{count}" for line, count in outer[number]["line_distribution"].items())
        for number in ("002", "003", "004")
    )
    new_external = (
        "外盘：The Odds API主来源因英锦标赛无赛事路由而0映射；Nowscore后备已按场次号、球队与开赛时间唯一映射3/3，取得40条合格赛前研究报价。"
        f"当前亚洲盘分布：{line_text}。这些报价用于校验盘口结构，但尚未升级为生产模型特征，不能单独授权正式方案。"
    )
    text = text.replace(old_external, new_external)
    old_formal = "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。"
    new_formal = (
        "已执行 `build_multi_play_betting_strategy.py --stake 100` 并通过终版编排校验。正式候选0组、正式台账新增0行；这不是授权拦截。"
        "002通过强热门市场筛选，但003、004的市场概率均低于0.52、赔率高于1.85，且没有模型支持的让球边际，无法组成合格正式串关。"
        "100元标准本金规则继续保留，只在正式候选成立时入账。"
    )
    text = text.replace(old_formal, new_formal)
    supplement = (
        "\n## 策略、影子与外盘审计补充\n\n"
        "- 正式策略：已运行；生产候选0组，正式投入0元，原因是生产门槛而非授权闸门。\n"
        "- 策略影子防冷：002主胜/平 + 003主胜/客胜，4注、1倍、虚拟本金8元。\n"
        "- 策略影子博高：002/003/004三场均取让平，1注、1倍、虚拟本金2元，组合赔率75.0092。\n"
        f"- 固定赔率影子：{fixed['selection']}，1注、1倍、虚拟本金2元，组合赔率{fixed['odds']:.4f}；已写入独立影子台账。\n"
        "- 邪修影子：003诺茨郡(-1)让负@1.43，1注、1倍、虚拟本金2元；只作市场撕裂观察。\n"
        f"- Nowscore后备：3/3唯一映射，外盘分布为{line_text}；主来源失败状态仍保留。\n"
        "- Supabase：本销售日未授权同步。\n"
    )
    if "## 策略、影子与外盘审计补充" not in text:
        text += supplement
    report_path.write_text(text, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-22.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for task in registry["tasks"]:
        if task["key"] == "2026-09-22|02:00|终版分析":
            task.update(
                {
                    "status": "completed",
                    "completed_at": ANALYSIS_AT,
                    "completion_status": "completed_ready_strategy_zero_formal_fixed_shadow_recorded_nowscore_3_of_3",
                    "artifact": str(audit_path.relative_to(ROOT)).replace("\\", "/"),
                    "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
                    "production_plan_rows": 0,
                    "production_ledger_write_performed": False,
                    "fixed_odds_shadow_rows_added": 1 if fixed["status"] == "recorded" else 0,
                }
            )
    registry["updated_at"] = ANALYSIS_AT
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(
        {
            "last_heartbeat_at": ANALYSIS_AT,
            "last_completed_stage": "2026-09-22 02:00终版批次002-004",
            "last_completed_at": ANALYSIS_AT,
            "last_stage_status": "completed_002_004_ready_strategy_zero_formal_fixed_shadow_recorded_nowscore_3_of_3",
            "last_stage_artifact": str(report_path.relative_to(ROOT)).replace("\\", "/"),
            "inner_outer_alignment_status": "2026-09-22_2112_primary_no_routed_sports_nowscore_mapped_3_of_3_research_available_production_feature_not_ready",
            "next_dynamic_task_key": None,
            "next_dynamic_task_at": None,
            "next_required_stage": "2026-09-23 10:00开售前预扫描；13:00复盘001-004",
            "next_required_at": "2026-09-23T10:00:00+08:00",
        }
    )
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": "completed",
        "matches": 3,
        "production_plan_rows": 0,
        "strategy_shadow_rows": 3,
        "fixed_shadow_status": fixed["status"],
        "nowscore_mapped": 3,
        "report": str(report_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
