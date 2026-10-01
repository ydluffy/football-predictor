from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "artifacts/data/football_automation_controller_state.json"


def main() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state.update(
        {
            "last_heartbeat_at": "2026-09-23T11:06:05+08:00",
            "last_completed_stage": "2026-09-23 11:05在售确认",
            "last_completed_at": "2026-09-23T11:06:05+08:00",
            "last_stage_status": "completed_confirm_three_on_sale_003_new_nowscore_3_of_3_no_ledger_write",
            "last_stage_artifact": "artifacts/betting/sporttery_sales_window_scan_2026-09-23_1106_confirm.md",
            "confirm_source_status": "2026-09-23_1106_official_3_on_sale_all_before_kickoff_four_play_fetch_ok_three_dynamic_groups_pending_schedule",
            "inner_outer_alignment_status": "2026-09-23_1106_primary_no_routed_sports_nowscore_mapped_3_of_3_research_available_production_feature_not_ready",
            "next_dynamic_task_key": "2026-09-23|13:30|终版分析",
            "next_dynamic_task_at": "2026-09-23T12:00:00+08:00",
            "next_required_stage": "2026-09-23 12:00终版分析001 中国亚 vs 阿联酋亚；13:00复盘2026-09-22销售日",
            "next_required_at": "2026-09-23T12:00:00+08:00",
        }
    )
    state["confirm_20260923"] = {
        "status": "completed",
        "completed_at": "2026-09-23T11:06:05+08:00",
        "fixture_count": 3,
        "on_sale": 3,
        "match_numbers": "001-003",
        "delta_from_preopen": "003_added; 001-002_remain",
        "official_four_play_fetch": "ok",
        "the_odds": "no_routed_sports_mapped0_of3",
        "nowscore_fallback": "complete_mapped3_of3_research_rows30_failures0_production_feature_not_ready",
        "dynamic_batches": "12:00_001;17:00_002;21:00_003",
        "ledger_write_performed": False,
        "registry": "artifacts/data/sporttery_task_registry_2026-09-23.json",
        "report": "artifacts/betting/sporttery_sales_window_scan_2026-09-23_1106_confirm.md",
        "supabase_sync": "not_authorized_for_2026-09-23",
    }
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "on_sale": 3, "next": "2026-09-23T12:00:00+08:00"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
