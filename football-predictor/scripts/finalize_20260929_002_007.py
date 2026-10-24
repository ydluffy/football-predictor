from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-29T16:05:57+08:00"
REPORT = "artifacts/betting/sporttery_final_analysis_2026-09-29_1605_002-007.md"
AUDIT = "artifacts/data/sporttery_final_analysis_2026-09-29_1605_002-007.json"
STRATEGY = "artifacts/data/production_strategy_2026-09-29_1605_002-007.json"
PLANS = "artifacts/data/production_strategy_plans_2026-09-29_1605_002-007.csv"
ORCHESTRATION = "artifacts/data/final_orchestration_validation_2026-09-29_1605_002-007.json"
FORMAL_LEDGER = "data/manual/betting_plan_ledger.csv"
FIXED_LEDGER = "data/manual/fixed_odds_shadow_ledger.csv"


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def read_csv(path: str) -> list[dict[str, str]]:
    with (ROOT / path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def append_unique(path: str, row: dict[str, str]) -> bool:
    target = ROOT / path
    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        existing = {item["plan_id"] for item in reader}
    if row["plan_id"] in existing:
        return False
    assert fieldnames is not None
    with target.open("a", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=fieldnames).writerow(row)
    return True


def main() -> None:
    strategy = load(STRATEGY)
    orchestration = load(ORCHESTRATION)
    audit = load(AUDIT)
    if not orchestration.get("ok") or strategy.get("production_plan_rows") != 2:
        raise ValueError("production strategy or orchestration validation failed")

    plans = read_csv(PLANS)
    formal = [p for p in plans if p["is_shadow"].lower() == "false"]
    if {p["plan_id"] for p in formal} != {"MULTI_PLAY_SAFE", "MULTI_PLAY_VALUE"}:
        raise ValueError("expected exactly SAFE and VALUE formal plans")

    stable_ids = {
        "MULTI_PLAY_SAFE": "SPORTTERY_20260929_002_007_SAFE",
        "MULTI_PLAY_VALUE": "SPORTTERY_20260929_002_007_VALUE",
    }
    added: list[str] = []
    formal_records: list[dict[str, object]] = []
    for plan in formal:
        stable_id = stable_ids[plan["plan_id"]]
        did_add = append_unique(FORMAL_LEDGER, {
            "date": "2026-09-29",
            "time_window": "16:05-17:45",
            "plan_id": stable_id,
            "plan_type": plan["plan_type"],
            "selections": plan["selections"],
            "stake": f'{float(plan["total_stake"]):.2f}',
            "estimated_odds": f'{float(plan["estimated_odds_min"]):.4f}',
            "actual_odds": "",
            "result": "待赛",
            "payout": "",
            "net_profit": "",
            "roi": "",
            "review_note": "17:45硬锁前冻结；每组本金100元；正式策略及编排校验通过",
        })
        if did_add:
            added.append(stable_id)
        formal_records.append({
            "plan_id": stable_id,
            "plan_type": plan["plan_type"],
            "selections": plan["selections"],
            "stake": float(plan["total_stake"]),
            "estimated_odds": float(plan["estimated_odds_min"]),
            "estimated_payout": float(plan["estimated_payout_min"]),
        })

    market_fixed = next(s for s in audit["shadow_schemes"] if s["id"] == "MULTI_PLAY_FIXED_ODDS_SHADOW")
    fixed_id = "FIXED_ODDS_SHADOW_20260929_16_05_002_007"
    fixed_added = append_unique(FIXED_LEDGER, {
        "date": "2026-09-29",
        "time_window": "16:05-17:45",
        "plan_id": fixed_id,
        "plan_type": "固定赔率观察/影子",
        "selections": market_fixed["selection"],
        "stake": "2.00",
        "estimated_odds": f'{float(market_fixed["omin"]):.4f}',
        "actual_odds": "",
        "result": "待赛",
        "payout": "",
        "net_profit": "",
        "roi": "",
        "review_note": "仅影子观察；与正式及邪修分开；不进入正式投注台账",
    })

    audit.update({
        "formal_plans": formal_records,
        "formal_plan_reason": "002-004形成两组通过生产资格闸门的正式二串一；005-007因生产输入不完整被明确排除",
        "production_strategy_executed": True,
        "production_strategy_audit": STRATEGY,
        "production_plan_rows": 2,
        "production_ledger_write_performed": bool(added),
        "production_ledger_plan_ids": list(stable_ids.values()),
        "orchestration_validation": orchestration,
        "fixed_odds_shadow": {
            "status": "recorded" if fixed_added else "already_recorded",
            "plan_id": fixed_id,
            "selection": market_fixed["selection"],
            "virtual_stake": 2.0,
            "odds": market_fixed["omin"],
            "ledger": FIXED_LEDGER,
            "production_ledger_write_performed": False,
        },
        "external_odds": {
            "primary_source": "the_odds_api",
            "primary_status": "quota_insufficient",
            "quota_remaining": 1,
            "estimated_route_cost": 12,
            "effective_source": "nowscore",
            "effective_status": "available_via_nowscore",
            "captured_at": "2026-09-29T16:08:00+08:00",
            "mapped_matches_all_day": 15,
            "captured_on_sale_all": 14,
            "captured_matches_batch": 6,
            "quote_rows_all": 1428,
            "asian_outer_rows_all": 238,
            "research_eligible_rows_all": 177,
            "failures": [],
            "per_match": {
                "002": "5 books Australia +1.25 and 9 at +1.5",
                "003": "5 books Fujieda +1 and 7 at +1.25",
                "004": "9 books Tochigi City +2",
                "005": "2 books Toyama +0.5, 9 at +0.75, 1 at +1",
                "006": "1 book Yamagata +1 and 12 at +1.25",
                "007": "6 books Japan Women -1.75 and 7 at -2",
            },
            "production_model_feature_ready": False,
        },
    })
    (ROOT / AUDIT).write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_path = ROOT / REPORT
    report = report_path.read_text(encoding="utf-8")
    report = report.replace(
        "外盘：鉴权探针HTTP 200，密钥有效，但当前仅余1 credit，不足以执行路由后的多市场刷新；本批0映射并排除。没有统一可核验的首发、伤停、xG或旅行负荷。",
        "外盘：The Odds API仅余1 credit，完整路由预计12 credits，未发送付费请求；捷报后备已完成本批6/6唯一映射并留存赛前亚洲盘。该数据只作研究对照，未升级为生产模型特征；没有统一可核验的首发、伤停、xG或旅行负荷。",
    )
    report = report.replace(
        "本报告器只产生逐场市场分析与影子观察方案，不决定正式方案数。正式候选必须以同批 `build_multi_play_betting_strategy.py --stake 100` 的审计结果为准；影子模型或外盘缺失不得单独将正式方案置零。",
        "已执行正式策略并通过编排校验：稳健方案为004客胜 + 002客胜，本金100元，估算赔率1.3542；价值方案为002客胜 + 003客胜，本金100元，估算赔率1.6592。两组均已在17:45硬锁前写入正式模拟台账。005-007因生产输入不完整，未进入正式组合。",
    )
    report += """

## 内外盘终版对照

- The Odds API：仅余1 credit，完整路由预计12 credits，未发起付费赔率请求。
- 捷报后备：当日15场唯一映射，本批002-007共6/6抓取成功；仅作研究对照，不作为正式模型特征。
- 002：澳大利亚+1.25（5家公司）/+1.5（9家公司），外盘保护深于体彩+1。
- 003：藤枝MYFC+1（5家公司）/+1.25（7家公司），与体彩+1方向一致、部分更深。
- 004：枥木城+2（9家公司），与体彩+2一致。
- 005：富山胜利+0.5（2家）/+0.75（9家）/+1（1家），主流浅于体彩+1。
- 006：山形山神+1（1家）/+1.25（12家），主流保护深于体彩+1。
- 007：日本女-1.75（6家）/-2（7家），与体彩-2基本一致。

## 冻结结论

- 正式稳健：004 广岛三箭客胜 + 002 巴西客胜；本金100元，估算赔率1.3542，估算返奖135.42元。
- 正式价值：002 巴西客胜 + 003 大阪樱花客胜；本金100元，估算赔率1.6592，估算返奖165.92元。
- 正式总投入200元；005-007未进入正式策略，原因是生产策略所需SPF/RQSPF完整性校验未通过。
- 固定赔率影子：002(+1)让负 + 004(+2)让负 + 006(+1)让负；虚拟本金2元，估算赔率7.9767，已单独登记。
- 邪修影子：007 日本女(-2)让负@2.24，虚拟本金2元；不写正式台账、不倍投、不追损。
"""
    report_path.write_text(report, encoding="utf-8")

    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-29.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    updated = 0
    for task in registry["tasks"]:
        if task["key"] == "2026-09-29|18:00-18:30|终版分析":
            task.update({
                "status": "completed",
                "updated_at": NOW,
                "completed_at": NOW,
                "completion_status": "completed_ready_two_formal_safe_value_fixed_shadow_nowscore_available",
                "artifact": AUDIT,
                "report": REPORT,
                "production_plan_rows": 2,
                "production_ledger_write_performed": bool(added),
                "production_plan_ids": list(stable_ids.values()),
                "formal_total_stake": 200.0,
                "fixed_odds_shadow_rows": 1,
                "fixed_odds_shadow_plan_id": fixed_id,
            })
            updated += 1
    if updated != 1:
        raise ValueError(f"expected one registry task, updated {updated}")
    registry["updated_at"] = NOW
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_final_002_007_two_formal",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-29 16:30终版批次002-007",
        "last_completed_at": NOW,
        "last_stage_status": "completed_ready_two_formal_fixed_shadow_nowscore_available",
        "last_stage_artifact": REPORT,
        "last_ledger_write_at": NOW,
        "inner_outer_alignment_status": "2026-09-29_1608_primary_quota_insufficient_nowscore_batch6_of6",
        "next_dynamic_task_key": "2026-09-29|02:45|终版分析",
        "next_dynamic_task_at": "2026-09-29T21:00:00+08:00",
        "next_required_stage": "2026-09-29 21:00终版批次008-014及015",
        "next_required_at": "2026-09-29T21:00:00+08:00",
    })
    state["final_20260929_002_007"] = {
        "status": "completed",
        "completed_at": NOW,
        "scope": "002-007",
        "official_captured_at": NOW,
        "gate": "READY_FOR_FINAL_ANALYSIS",
        "formal_strategy_executed": True,
        "formal_plan_count": 2,
        "formal_plan_ids": list(stable_ids.values()),
        "formal_total_stake": 200.0,
        "fixed_odds_shadow_count": 1,
        "fixed_odds_shadow_plan_id": fixed_id,
        "fixed_odds_shadow_stake": 2.0,
        "contrarian_shadow_count": 1,
        "external_odds": "the_odds_quota_insufficient_nowscore_batch6_of6_research_only",
        "production_ledger_write_performed": bool(added),
        "production_ledger_sha256": hashlib.sha256((ROOT / FORMAL_LEDGER).read_bytes()).hexdigest(),
        "report": REPORT,
        "review_due_at": "2026-09-30T13:00:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-29",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "completed",
        "scope": "002-007",
        "formal_added": added,
        "formal_total_stake": 200,
        "fixed_shadow_added": fixed_added,
        "next": "2026-09-29T21:00:00+08:00",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
