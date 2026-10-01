from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-30T11:05:16+08:00"
SCAN = "artifacts/data/sporttery_sales_window_scan_2026-09-30_1105_confirm.json"
REPORT = "artifacts/betting/sporttery_sales_window_scan_2026-09-30_1105_confirm.md"
REGISTRY = "artifacts/data/sporttery_task_registry_2026-09-30.json"
STATE = ROOT / "artifacts/data/football_automation_controller_state.json"


def main() -> None:
    scan = json.loads((ROOT / SCAN).read_text(encoding="utf-8"))
    registry = json.loads((ROOT / REGISTRY).read_text(encoding="utf-8"))
    ext = scan["external_odds"]
    ns = scan["sources"]["nowscore_fallback"]
    if scan["stage"] != "confirm" or scan["summary"]["on_sale"] != 2:
        raise ValueError("unexpected 2026-09-30 confirmation scan")
    if len(registry["tasks"]) != 2 or scan["ledger_gate"]["write_performed"]:
        raise ValueError("confirmation queue or ledger gate is inconsistent")
    if ns["mapped_count"] != 2 or ns["captured_match_count"] != 2 or ns["failures"]:
        raise ValueError("Nowscore fallback coverage is incomplete")

    state = json.loads(STATE.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_confirm_20260930_2_on_sale_two_batches",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-30 11:05开售确认与动态分组",
        "last_completed_at": NOW,
        "last_stage_status": "completed_confirm_2_on_sale_nowscore_available_no_ledger_write",
        "last_stage_artifact": REPORT,
        "confirm_source_status": "2026-09-30_1105_official_2_on_sale_four_play_fetch_ok_two_dynamic_groups_heartbeat_queue",
        "inner_outer_alignment_status": "2026-09-30_1107_primary_no_routed_sports_nowscore_mapped2_of2_research_rows26",
        "next_dynamic_task_key": "2026-09-30|14:00|终版分析",
        "next_dynamic_task_at": "2026-09-30T12:30:00+08:00",
        "next_required_stage": "2026-09-30 12:30终版001；13:00复盘2026-09-29",
        "next_required_at": "2026-09-30T12:30:00+08:00",
        "pending_reschedule": True,
        "pending_reschedule_reason": "fixed 30-minute heartbeat remains active; registry is the work queue and the next due batch is 001 at 12:30",
    })
    state["confirm_20260930"] = {
        "status": "completed",
        "completed_at": NOW,
        "official_captured_at": NOW,
        "fixture_count": 2,
        "on_sale": 2,
        "stopped": 0,
        "match_numbers": ["001", "002"],
        "delta_from_preopen": "both prelisted matches remained on_sale; no new fixtures were published",
        "official_four_play_fetch": "ok",
        "the_odds": "no_routed_sports_for_asian_games_football",
        "nowscore_fallback": "complete_mapped2_of2_quote_rows204_asian_rows34_research_rows26_failures0",
        "effective_external_market": ext["effective_status"],
        "production_model_feature_ready": False,
        "dynamic_batches": "12:30_001;17:00_002",
        "ledger_write_performed": False,
        "registry": REGISTRY,
        "report": REPORT,
        "supabase_sync": "not_authorized_for_2026-09-30",
    }
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "on_sale": 2, "tasks": 2, "next": "2026-09-30T12:30:00+08:00"}))


if __name__ == "__main__":
    main()
