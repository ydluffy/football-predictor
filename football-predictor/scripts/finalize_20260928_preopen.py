from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-28T10:05:23+08:00"


def main() -> None:
    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_preopen_20260928_empty_not_yet_published",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-28 10:00开售前预扫描",
        "last_completed_at": NOW,
        "last_stage_status": "completed_preopen_empty_not_yet_published",
        "last_stage_artifact": "artifacts/betting/sporttery_sales_window_scan_2026-09-28_1005_preopen.md",
        "next_dynamic_task_key": None,
        "next_dynamic_task_at": None,
        "next_required_stage": "2026-09-28 11:05开售确认；13:00复盘2026-09-27",
        "next_required_at": "2026-09-28T11:05:00+08:00",
        "pending_reschedule": True,
        "pending_reschedule_reason": "automation_update interface unavailable; fixed heartbeat remains active for the 11:05 confirmation",
    })
    state["preopen_20260928"] = {
        "status": "completed",
        "completed_at": NOW,
        "official_captured_at": NOW,
        "fixture_count": 0,
        "sale_status": "prelisted",
        "message": "开售前尚未发布",
        "official_four_play_fetch": "ok",
        "ledger_write_performed": False,
        "report": "artifacts/betting/sporttery_sales_window_scan_2026-09-28_1005_preopen.md",
        "confirm_due_at": "2026-09-28T11:05:00+08:00",
        "supabase_sync": "not_authorized_for_2026-09-28",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "fixtures": 0, "next": "2026-09-28T11:05:00+08:00"}))


if __name__ == "__main__":
    main()
