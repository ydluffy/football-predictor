from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-28T11:05:54+08:00"


def main() -> None:
    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_confirm_20260928_8_on_sale",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-28 11:05开售确认",
        "last_completed_at": NOW,
        "last_stage_status": "completed_confirm_8_on_sale_nowscore_available",
        "last_stage_artifact": "artifacts/betting/sporttery_sales_window_scan_2026-09-28_1105_confirm.md",
        "confirm_source_status": "2026-09-28_1105_official_8_on_sale_four_play_fetch_ok_three_dynamic_groups_heartbeat_queue",  # pragma: allowlist secret - non-secret status or character set
        "inner_outer_alignment_status": "2026-09-28_1107_primary_quota_insufficient_nowscore_mapped8_of8_research_rows109",  # pragma: allowlist secret - non-secret status or character set
        "next_dynamic_task_key": "2026-09-28|18:25-19:00|终版分析",
        "next_dynamic_task_at": "2026-09-28T16:55:00+08:00",
        "next_required_stage": "2026-09-28 13:00复盘2026-09-27；16:55终版001-002",
        "next_required_at": "2026-09-28T13:00:00+08:00",
        "pending_reschedule": True,
        "pending_reschedule_reason": "automation_update interface unavailable; fixed heartbeat remains active and registry tasks remain pending_schedule",
    })
    state["confirm_20260928"] = {
        "status": "completed",
        "completed_at": NOW,
        "official_captured_at": NOW,
        "fixture_count": 8,
        "on_sale": 8,
        "stopped": 0,
        "match_numbers": "001-008",
        "delta_from_preopen": "10:05 preopen empty; 8 fixtures published and confirmed on_sale at 11:05",
        "official_four_play_fetch": "ok",
        "the_odds": "quota_insufficient_remaining1_estimated12_mapped0_of8",
        "nowscore_fallback": "complete_mapped8_of8_quote_rows816_asian_rows136_research_rows109_failures0",
        "effective_external_market": "available_via_nowscore_production_model_feature_not_ready",
        "football_data_org": "ok_matches0_standings132_failures0",
        "dynamic_batches": "16:55_001-002;21:00_003;21:00_004-008",
        "ledger_write_performed": False,
        "registry": "artifacts/data/sporttery_task_registry_2026-09-28.json",
        "report": "artifacts/betting/sporttery_sales_window_scan_2026-09-28_1105_confirm.md",
        "supabase_sync": "not_authorized_for_2026-09-28",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "on_sale": 8, "next": "2026-09-28T13:00:00+08:00"}))


if __name__ == "__main__":
    main()
