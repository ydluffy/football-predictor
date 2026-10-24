import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
scan_path = ROOT / "artifacts/data/sporttery_sales_window_scan_2026-09-27_1006_preopen.json"

state = json.loads(state_path.read_text(encoding="utf-8"))
scan = json.loads(scan_path.read_text(encoding="utf-8"))
fixtures = scan["fixtures"]
match_numbers = [item["match_number"] for item in fixtures]

state.update({
    "status": "completed_preopen_5_prelisted_no_ledger_write",
    "last_heartbeat_at": "2026-09-27T10:06:55+08:00",
    "last_completed_stage": "2026-09-27 10:00开售前预扫描",
    "last_completed_at": "2026-09-27T10:09:00+08:00",
    "last_stage_status": "completed_preopen_5_prelisted_no_ledger_write",
    "last_stage_artifact": "artifacts/betting/sporttery_sales_window_scan_2026-09-27_1006_preopen.md",
    "preopen_source_status": {
        "sales_day": "2026-09-27",
        "official_fixture_count": len(fixtures),
        "official_four_play_fetch": "ok",
        "sale_status": "prelisted",
        "requires_confirm_at": "2026-09-27T11:05:00+08:00",
        "note": "10:00官网数据仅为预列，不能据此认定正式在售；024、025于10:30开赛且缺SPF/RQSPF覆盖，只留预列档案。",
    },
    "next_dynamic_task_key": None,
    "next_dynamic_task_at": None,
    "next_required_stage": "2026-09-27 11:05在售确认；13:00复盘2026-09-26销售日",
    "next_required_at": "2026-09-27T11:05:00+08:00",
    "pending_reschedule": True,
    "pending_reschedule_reason": "automation_update interface unavailable; fixed heartbeat remains active",
})
state["preopen_20260927"] = {
    "status": "completed",
    "completed_at": "2026-09-27T10:09:00+08:00",
    "official_captured_at": scan["scanned_at"],
    "fixture_count": len(fixtures),
    "match_numbers": match_numbers,
    "sale_status": "prelisted",
    "official_four_play_fetch": "ok",
    "ledger_write_performed": False,
    "early_kickoff_archival_only": ["024", "025"],
    "report": "artifacts/betting/sporttery_sales_window_scan_2026-09-27_1006_preopen.md",
    "confirm_due_at": "2026-09-27T11:05:00+08:00",
    "supabase_sync": "not_authorized_for_2026-09-27",
}

state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
