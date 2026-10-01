import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
state_path = ROOT / "artifacts" / "data" / "football_automation_controller_state.json"
scan_path = ROOT / "artifacts" / "data" / "sporttery_sales_window_scan_2026-09-24_1006_preopen.json"

state = json.loads(state_path.read_text(encoding="utf-8"))
scan = json.loads(scan_path.read_text(encoding="utf-8"))
fixtures = scan.get("fixtures", [])
match_numbers = [item["match_number"] for item in fixtures]

state.update(
    {
        "status": "completed_preopen_8_prelisted_no_ledger_write",
        "last_heartbeat_at": "2026-09-24T10:06:54+08:00",
        "last_completed_stage": "2026-09-24 10:00开售前预扫描",
        "last_completed_at": "2026-09-24T10:10:09+08:00",
        "last_stage_status": "completed_preopen_8_prelisted_no_ledger_write",
        "last_stage_artifact": "artifacts/betting/sporttery_sales_window_scan_2026-09-24_1006_preopen.md",
        "preopen_source_status": {
            "sales_day": "2026-09-24",
            "official_fixture_count": len(fixtures),
            "official_four_play_fetch": "ok",
            "sale_status": "prelisted",
            "requires_confirm_at": "2026-09-24T11:05:00+08:00",
            "note": "10:00官网数据仅为预列，不能据此认定正式在售。",
        },
        "next_dynamic_task_key": None,
        "next_dynamic_task_at": None,
        "next_required_stage": "2026-09-24 11:05在售确认；13:00复盘2026-09-23销售日",
        "next_required_at": "2026-09-24T11:05:00+08:00",
        "preopen_20260924": {
            "status": "completed",
            "completed_at": "2026-09-24T10:10:09+08:00",
            "official_captured_at": scan["scanned_at"],
            "fixture_count": len(fixtures),
            "match_numbers": match_numbers,
            "sale_status": "prelisted",
            "all_before_kickoff": all(
                item.get("sale_status") == "prelisted" for item in fixtures
            ),
            "official_four_play_fetch": "ok",
            "ledger_write_performed": False,
            "report": "artifacts/betting/sporttery_sales_window_scan_2026-09-24_1006_preopen.md",
            "confirm_due_at": "2026-09-24T11:05:00+08:00",
            "supabase_sync": "not_authorized_for_2026-09-24",
        },
    }
)

state_path.write_text(
    json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
