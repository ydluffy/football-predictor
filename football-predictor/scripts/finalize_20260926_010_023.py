from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-26T22:20:00+08:00"


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def append_unique(path: Path, row: dict[str, str], id_field: str = "plan_id") -> bool:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        existing = {item[id_field] for item in reader}
    if row[id_field] in existing:
        return False
    assert fieldnames is not None
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writerow(row)
    return True


def main() -> None:
    report_path = ROOT / "artifacts/betting/sporttery_final_analysis_2026-09-26_2206_010-023.md"
    audit_path = ROOT / "artifacts/data/sporttery_final_analysis_2026-09-26_2206_010-023.json"
    strategy_path = ROOT / "artifacts/data/sporttery_final_strategy_2026-09-26_2206_010-023_audit.json"
    plans_path = ROOT / "artifacts/data/sporttery_final_strategy_2026-09-26_2206_010-023_plans.csv"
    orchestration_path = ROOT / "artifacts/data/sporttery_final_orchestration_2026-09-26_2206_010-023.json"
    formal_ledger = ROOT / "data/manual/betting_plan_ledger.csv"
    fixed_ledger = ROOT / "data/manual/fixed_odds_shadow_ledger.csv"

    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    orchestration = json.loads(orchestration_path.read_text(encoding="utf-8"))
    assert strategy["production_plan_rows"] == 2 and orchestration["ok"] is True
    with plans_path.open("r", encoding="utf-8-sig", newline="") as handle:
        plans = list(csv.DictReader(handle))
    formal = [row for row in plans if row["is_shadow"].lower() == "false"]
    fixed = next(row for row in plans if row["plan_id"] == "MULTI_PLAY_FIXED_ODDS_SHADOW")
    assert len(formal) == 2

    stable_ids = {
        "MULTI_PLAY_SAFE": "SPORTTERY_20260926_010_023_SAFE",
        "MULTI_PLAY_VALUE": "SPORTTERY_20260926_010_023_VALUE",
    }
    formal_added: list[str] = []
    formal_records: list[dict[str, object]] = []
    for plan in formal:
        stable_id = stable_ids[plan["plan_id"]]
        added = append_unique(formal_ledger, {
            "date": "2026-09-26", "time_window": "22:00-22:45", "plan_id": stable_id,
            "plan_type": plan["plan_type"], "selections": plan["selections"],
            "stake": f'{float(plan["total_stake"]):.2f}',
            "estimated_odds": f'{float(plan["estimated_odds_min"]):.4f}',
            "actual_odds": "", "result": "待赛", "payout": "", "net_profit": "", "roi": "",
            "review_note": "22:45硬锁前冻结；每组本金100元；正式策略及编排校验通过",
        })
        if added:
            formal_added.append(stable_id)
        formal_records.append({
            "plan_id": stable_id, "plan_type": plan["plan_type"], "selections": plan["selections"],
            "stake": float(plan["total_stake"]), "estimated_odds": float(plan["estimated_odds_min"]),
            "estimated_payout": float(plan["estimated_payout_min"]),
        })

    fixed_id = "FIXED_ODDS_SHADOW_20260926_22_06_010_023"
    fixed_added = append_unique(fixed_ledger, {
        "date": "2026-09-26", "time_window": "22:06-22:45", "plan_id": fixed_id,
        "plan_type": "固定赔率观察/影子", "selections": fixed["selections"],
        "stake": f'{float(fixed["total_stake"]):.2f}',
        "estimated_odds": f'{float(fixed["estimated_odds_min"]):.4f}',
        "actual_odds": "", "result": "待赛", "payout": "", "net_profit": "", "roi": "",
        "review_note": "22:45硬锁前冻结；仅影子观察；不进入正式投注台账",
    })

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit.update({
        "formal_plans": formal_records,
        "formal_plan_reason": "强制正式策略产出稳健与价值各1组，均通过生产资格闸门和编排校验",
        "production_strategy_executed": True,
        "production_strategy_audit": rel(strategy_path),
        "production_plan_rows": 2,
        "production_ledger_write_performed": bool(formal_added),
        "production_ledger_plan_ids": list(stable_ids.values()),
        "orchestration_validation": orchestration,
        "fixed_odds_shadow_ledger": {"plan_id": fixed_id, "write_performed": fixed_added},
        "external_odds": {
            "primary_source": "the_odds_api", "primary_status": "quota_insufficient",
            "effective_source": "nowscore", "effective_status": "available_via_nowscore",
            "captured_at": "2026-09-26T22:08:02+08:00", "mapped_matches_all": 23,
            "captured_on_sale_all": 15, "batch_mapped": 14, "batch_captured": 14,
            "quote_rows_all": 1530, "asian_outer_rows_all": 255,
            "research_eligible_rows_all": 204, "failures": [],
            "production_model_feature_ready": False,
        },
    })
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = report_path.read_text(encoding="utf-8")
    report = report.replace(
        "外盘：鉴权探针HTTP 200，密钥有效，但当前仅余1 credit，不足以执行路由后的多市场刷新；本批0映射并排除。没有统一可核验的首发、伤停、xG或旅行负荷。",
        "外盘：The Odds API仅余1 credit，低于预计12 credits，未发送付费请求；捷报后备已完成本批14/14唯一映射并留存赛前报价。外盘仅作对照证据，尚未升级为生产模型特征；没有统一可核验的首发、伤停、xG或旅行负荷。",
    )
    report = report.replace(
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。",
        "已执行强制正式策略并通过编排校验：稳健方案为011主胜 + 015客胜，本金100元，估算赔率1.4145；价值方案为015客胜 + 022主胜，本金100元，估算赔率1.5744。两组均已在22:45硬锁前写入正式模拟台账。",
    )
    report += f"""

## 冻结结论

- 正式稳健：011 冰岛 vs 爱沙尼亚 主胜 + 015 北马其顿 vs 瑞士 客胜；本金100元，估算赔率1.4145，估算返奖141.45元。
- 正式价值：015 北马其顿 vs 瑞士 客胜 + 022 纳什维尔 vs 多伦多 主胜；本金100元，估算赔率1.5744，估算返奖157.44元。
- 正式总投入200元；两组均已写入本地正式模拟台账，等待赛果复盘。
- 固定赔率影子：{fixed['selections']}；虚拟本金2元，估算赔率7.9827，单独写入影子台账。
- 邪修影子：023 盐湖城(-1)让负@1.50，虚拟本金2元，只作理论观察，不写正式台账、不倍投、不追损。
- 捷报后备本批覆盖14/14；The Odds API主状态仍为额度不足。
"""
    report_path.write_text(report, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-26.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    completed_keys = {
        "2026-09-26|00:00|终版分析", "2026-09-26|02:00-02:45|终版分析",
        "2026-09-26|04:30|终版分析", "2026-09-26|07:00-08:30|终版分析",
        "2026-09-26|09:30|终版分析", "2026-09-26|22:30-00:00|终版分析",
    }
    for task in registry["tasks"]:
        if task["key"] in completed_keys:
            task.update({
                "status": "completed", "completed_at": NOW,
                "completion_status": "completed_ready_two_formal_safe_value_nowscore_available",
                "artifact": rel(audit_path), "report": rel(report_path),
                "production_plan_rows": 2, "production_ledger_write_performed": bool(formal_added),
                "production_plan_ids": list(stable_ids.values()), "fixed_odds_shadow_plan_id": fixed_id,
            })
    registry["updated_at"] = NOW
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_final_010_023_two_formal", "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-26 22:00终版批次010-023及晚间兜底",
        "last_completed_at": NOW, "last_stage_status": "complete",
        "last_stage_artifact": rel(report_path), "last_ledger_write_at": NOW,
        "next_required_stage": "2026-09-27 10:00开售前预扫描",
        "next_required_at": "2026-09-27T10:00:00+08:00",
        "next_dynamic_task_key": None, "next_dynamic_task_at": None,
        "inner_outer_alignment_status": "2026-09-26_2208_primary_quota_insufficient_nowscore_batch_mapped14_of14",  # pragma: allowlist secret - non-secret status or character set
    })
    state["final_20260926_010_023"] = {
        "status": "completed", "completed_at": NOW, "scope": "010-023",
        "formal_strategy_executed": True, "formal_plan_count": 2,
        "formal_plan_ids": list(stable_ids.values()), "formal_total_stake": 200.0,
        "shadow_scheme_count": len(audit.get("shadow_schemes", [])),
        "fixed_odds_shadow_plan_id": fixed_id,
        "external_odds": "the_odds_quota_insufficient_nowscore_mapped14_of14",
        "production_ledger_write_performed": bool(formal_added), "report": rel(report_path),
        "review_due_at": "2026-09-27T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-26",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "completed", "scope": "010-023", "formal_rows": 2,
        "formal_added": formal_added, "fixed_shadow_added": fixed_added,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
