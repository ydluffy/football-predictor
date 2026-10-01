from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-21"
COMPLETED_AT = "2026-09-22T13:12:00+08:00"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    result_rows = read_csv(ROOT / "artifacts/data/sporttery_results_2026-09-21.csv")
    matches = [
        row
        for row in result_rows
        if row["date"] == DAY
        and row["match_number"] == "周一001"
        and row["home_team"] == "中国女"
        and row["away_team"] == "菲律宾女"
    ]
    assert len(matches) == 1, f"expected one official result, found {len(matches)}"
    result = matches[0]
    assert result["status"] == "已完成"

    formal = [
        row
        for row in read_csv(ROOT / "data/manual/betting_plan_ledger.csv")
        if row.get("date") == DAY
    ]
    fixed = [
        row
        for row in read_csv(ROOT / "data/manual/fixed_odds_shadow_ledger.csv")
        if row.get("date") == DAY
    ]
    shadow_predictions = [
        row
        for row in read_csv(ROOT / "data/manual/shadow_prediction_ledger_v2.csv")
        if row.get("sales_day") == DAY
    ]
    shadow_portfolios = [
        row
        for row in read_csv(ROOT / "data/manual/shadow_portfolio_ledger_v2.csv")
        if row.get("sales_day") == DAY
    ]
    assert not formal and not fixed and not shadow_predictions and not shadow_portfolios

    audit = {
        "sales_day": DAY,
        "reviewed_at": COMPLETED_AT,
        "status": "completed_official_result_only_no_frozen_predictions_or_plans",
        "official_match_count": 1,
        "official_result": result,
        "prediction_coverage": "0/1",
        "missing_prediction": ["001"],
        "formal_summary": {
            "plans": 0,
            "hits": 0,
            "stake": 0.0,
            "payout": 0.0,
            "net": 0.0,
            "roi": None,
        },
        "fixed_odds_shadow_summary": {
            "plans": 0,
            "stake": 0.0,
            "payout": 0.0,
            "net": 0.0,
            "roi": None,
        },
        "shadow_prediction_rows": 0,
        "shadow_portfolio_rows": 0,
        "schedule_failure": {
            "task_key": "2026-09-21|15:00|终版分析",
            "scheduled_run_at": "2026-09-21T13:30:00+08:00",
            "hard_lock": "2026-09-21T14:45:00+08:00",
            "detected_at": "2026-09-21T15:07:00+08:00",
            "reason": "heartbeat_next_trigger_arrived_after_hard_lock_and_kickoff",
            "post_lock_backfill": "prohibited_and_not_performed",
        },
        "sources": [
            "artifacts/data/sporttery_results_2026-09-21.csv",
            "artifacts/data/sporttery_sales_window_scan_2026-09-21_1312_confirm.json",
            "artifacts/data/sporttery_task_registry_2026-09-21.json",
            "artifacts/data/missed_final_audit_2026-09-21_001.json",
            "data/manual/betting_plan_ledger.csv",
            "data/manual/fixed_odds_shadow_ledger.csv",
            "data/manual/shadow_prediction_ledger_v2.csv",
            "data/manual/shadow_portfolio_ledger_v2.csv",
        ],
        "supabase_sync": "not_authorized_for_2026-09-21",
    }

    json_path = ROOT / "artifacts/data/sporttery_full_review_2026-09-21_1300_detailed.json"
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    markdown = f"""# 2026-09-21销售日详细复盘

官方赛果覆盖1/1；冻结终版预测覆盖0/1。当天没有正式、固定赔率或组合影子方案入账，因此投入0.00元、返奖0.00元、净收益0.00元，ROI不适用。未获当日Supabase同步授权。

## 逐场核验

| 编号 | 赛事 | 比赛 | 半场 | 全场 | SPF赛果 | 让球及赛果 | 复盘结论 |
|---|---|---|---:|---:|---|---|---|
| 001 | {result['competition']} | {result['home_team']} vs {result['away_team']} | {result['half_time_score']} | {result['full_time_score']} | {result['spf_result']} | {result['handicap']} / {result['rqspf_result']} | 无冻结赛前预测，只核实官方赛果，不计算预测命中率 |

## 方案与台账

| 台账类别 | 冻结记录 | 投入 | 返奖 | 净收益 | ROI |
|---|---:|---:|---:|---:|---|
| 正式模拟方案 | 0 | 0.00 | 0.00 | 0.00 | 不适用 |
| 固定赔率影子 | 0 | 0.00 | 0.00 | 0.00 | 不适用 |
| 模型预测影子 | 0 | — | — | — | 不适用 |
| 组合影子 | 0 | 0.00 | 0.00 | 0.00 | 不适用 |

## 调度与归因

- 终版任务原定北京时间13:30执行，硬锁14:45，比赛15:00开赛。
- 下一次实际心跳在15:07才到达，已经越过硬锁和开赛时间；注册表将任务标记为`failed`。
- 按赛前证据规则，未事后补造预测、赔率快照或投注方案，也未向任何台账追加记录。
- 这一天不能评价模型命中率；0元净收益不等于0% ROI，正确口径是ROI不适用。
- 详细故障证据：`artifacts/data/missed_final_audit_2026-09-21_001.json`。

结构化审计：`artifacts/data/sporttery_full_review_2026-09-21_1300_detailed.json`
"""
    markdown_path = ROOT / "artifacts/reviews/sporttery_full_review_2026-09-21_1300_detailed.md"
    markdown_path.write_text(markdown, encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(
        {
            "last_heartbeat_at": COMPLETED_AT,
            "last_completed_stage": "2026-09-22 13:00前一销售日复盘",
            "last_completed_at": COMPLETED_AT,
            "last_stage_status": "completed_review_20260921_official_1_of_1_no_frozen_predictions_or_plans_roi_not_applicable",
            "last_stage_artifact": "artifacts/reviews/sporttery_full_review_2026-09-21_1300_detailed.md",
            "last_reviewed_sales_day": DAY,
            "last_review_artifact": "artifacts/reviews/sporttery_full_review_2026-09-21_1300_detailed.md",
            "next_dynamic_task_key": "2026-09-22|18:00|终版分析",
            "next_dynamic_task_at": "2026-09-22T16:30:00+08:00",
            "next_required_stage": "2026-09-22 16:30终版分析001 韩国亚 vs 沙特亚",
            "next_required_at": "2026-09-22T16:30:00+08:00",
        }
    )
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "official_matches": 1,
                "score": result["full_time_score"],
                "formal_plans": 0,
                "fixed_shadow_plans": 0,
                "shadow_predictions": 0,
                "shadow_portfolios": 0,
                "report": str(markdown_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
