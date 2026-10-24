from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-30T10:05:45+08:00"
SCAN = "artifacts/data/sporttery_sales_window_scan_2026-09-30_1005_preopen.json"
REPORT = "artifacts/betting/sporttery_sales_window_scan_2026-09-30_1005_preopen.md"
STATE = ROOT / "artifacts/data/football_automation_controller_state.json"


def main() -> None:
    scan = json.loads((ROOT / SCAN).read_text(encoding="utf-8"))
    if scan["stage"] != "preopen" or scan["summary"]["prelisted"] != 2:
        raise ValueError("unexpected 2026-09-30 preopen scan")
    if scan["ledger_gate"]["write_performed"]:
        raise ValueError("preopen scan must not write the ledger")
    numbers = [item["match_number"] for item in scan["fixtures"]]
    if numbers != ["001", "002"]:
        raise ValueError(f"unexpected match numbers: {numbers}")

    state = json.loads(STATE.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_preopen_20260930_two_prelisted",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-30 10:00开售前预扫描",
        "last_completed_at": NOW,
        "last_stage_status": "completed_preopen_two_prelisted_no_ledger_write",
        "last_stage_artifact": REPORT,
        "preopen_source_status": {
            "sales_day": "2026-09-30",
            "official_fixture_count": 2,
            "match_numbers": numbers,
            "official_four_play_fetch": "ok",
            "sale_status": "prelisted",
            "requires_confirm_at": "2026-09-30T11:05:00+08:00",
            "early_match_guard": "001 kickoff 14:00; confirmation must create an early final task before its hard lock",
            "note": "10:05官网数据仅为预列，不能据此认定正式在售。",
        },
        "next_dynamic_task_key": None,
        "next_dynamic_task_at": None,
        "next_required_stage": "2026-09-30 11:05开售确认；13:00复盘2026-09-29",
        "next_required_at": "2026-09-30T11:05:00+08:00",
        "pending_reschedule": True,
        "pending_reschedule_reason": "fixed 30-minute heartbeat remains active; next legal stage is 11:05 confirmation",
    })
    state["preopen_20260930"] = {
        "status": "completed",
        "completed_at": NOW,
        "official_captured_at": NOW,
        "fixture_count": 2,
        "match_numbers": numbers,
        "sale_status": "prelisted",
        "official_four_play_fetch": "ok",
        "ledger_write_performed": False,
        "report": REPORT,
        "confirm_due_at": "2026-09-30T11:05:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-30",
    }
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "fixtures": 2, "next": "2026-09-30T11:05:00+08:00"}))


if __name__ == "__main__":
    main()
