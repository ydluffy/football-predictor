from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DETECTED_AT = "2026-09-27T23:49:27+08:00"
TASK_KEY = "2026-09-27|22:00|004-009终版"
AUDIT = "artifacts/data/missed_final_audit_2026-09-27_004-009.json"
REPORT = "artifacts/betting/missed_final_2026-09-27_004-009.md"


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def main() -> None:
    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-27.json"
    registry = load("artifacts/data/sporttery_task_registry_2026-09-27.json")
    tasks = [task for task in registry["tasks"] if task["key"] == TASK_KEY]
    if len(tasks) != 1:
        raise ValueError(f"expected one late-final task, found {len(tasks)}")
    task = tasks[0]
    audit = {
        "schema_version": 1,
        "sales_day": "2026-09-27",
        "stage": "final",
        "scope": "004-009",
        "status": "expired_missed",
        "detected_at": DETECTED_AT,
        "scheduled_at": task["run_at"],
        "hard_lock": task["hard_lock"],
        "sales_cutoff": task["sales_cutoff"],
        "match_numbers": task["match_numbers"],
        "matches": task["matches"],
        "reason": "heartbeat arrived after the 22:45 hard lock and 23:00 sales cutoff",
        "last_pre_lock_official_snapshot": "artifacts/data/sporttery_sales_window_scan_2026-09-27_1609_confirm.json",
        "last_snapshot_captured_at": "2026-09-27T16:09:45+08:00",
        "post_lock_backfill": False,
        "formal_plan_generated": False,
        "production_ledger_write_performed": False,
        "fixed_shadow_write_performed": False,
        "contrarian_shadow_write_performed": False,
        "supabase_sync": "not_authorized_for_2026-09-27",
    }
    audit_path = ROOT / AUDIT
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = """# 2026-09-27 体彩004—009终版过锁留档

检测时间：2026-09-27T23:49:27+08:00。

本批计划22:00执行，硬锁22:45，销售截止23:00。本次心跳到达时已经同时超过硬锁和销售截止，因此严格禁止补写赛前预测、正式方案、固定赔率影子或邪修影子。

## 留档范围

- 004 丹麦 vs 威尔士（00:00）
- 005 塞尔维亚 vs 荷兰（00:00）
- 006 奥地利 vs 科索沃（00:00）
- 007 德国 vs 希腊（02:45）
- 008 挪威 vs 葡萄牙（02:45）
- 009 哥伦布 vs 迈国际（07:00）

最后一个硬锁前官方快照为16:09:45，只能作为早期历史证据，不能冒充22:00终版。正式台账新增0条，固定赔率和邪修影子新增0条；明日复盘只处理已有赛前记录，不事后补造。
"""
    report_path = ROOT / REPORT
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    task.update({
        "status": "expired_missed",
        "updated_at": DETECTED_AT,
        "completed_at": DETECTED_AT,
        "completion_status": "expired_after_hard_lock_and_sales_cutoff_no_backfill",
        "artifact": AUDIT,
        "report": REPORT,
        "production_plan_rows": 0,
        "production_ledger_write_performed": False,
        "fixed_odds_shadow_rows": 0,
    })
    registry["updated_at"] = DETECTED_AT
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = load("artifacts/data/football_automation_controller_state.json")
    state.update({
        "status": "expired_missed_final_004_009_no_post_lock_backfill",
        "last_heartbeat_at": DETECTED_AT,
        "last_failed_task_key": TASK_KEY,
        "last_failed_at": DETECTED_AT,
        "last_stage_status": "expired_after_hard_lock_and_sales_cutoff_no_backfill",
        "last_stage_artifact": REPORT,
        "next_dynamic_task_key": None,
        "next_dynamic_task_at": None,
        "next_required_stage": "2026-09-28 10:00开售前预扫描；13:00复盘2026-09-27",
        "next_required_at": "2026-09-28T10:00:00+08:00",
        "pending_reschedule": True,
        "pending_reschedule_reason": "automation_update interface unavailable; fixed heartbeat remains active for the next daily cycle",
    })
    state["missed_final_20260927_004_009"] = audit
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "expired_missed", "task": TASK_KEY, "next": "2026-09-28T10:00:00+08:00"}, ensure_ascii=True))


if __name__ == "__main__":
    main()
