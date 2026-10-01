from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-29T11:05:22+08:00"
SCAN = "artifacts/data/sporttery_sales_window_scan_2026-09-29_1105_confirm.json"
REPORT = "artifacts/betting/sporttery_sales_window_scan_2026-09-29_1105_confirm.md"
REGISTRY = "artifacts/data/sporttery_task_registry_2026-09-29.json"
STATE = ROOT / "artifacts/data/football_automation_controller_state.json"


def main() -> None:
    scan = json.loads((ROOT / SCAN).read_text(encoding="utf-8"))
    registry = json.loads((ROOT / REGISTRY).read_text(encoding="utf-8"))
    ext = scan["external_odds"]
    ns = scan["sources"]["nowscore_fallback"]
    if scan["stage"] != "confirm" or scan["summary"]["on_sale"] != 15:
        raise ValueError("unexpected 2026-09-29 confirmation scan")
    if len(registry["tasks"]) != 4 or scan["ledger_gate"]["write_performed"]:
        raise ValueError("confirmation queue or ledger gate is inconsistent")
    if ns["mapped_count"] != 15 or ns["failures"]:
        raise ValueError("Nowscore fallback coverage is incomplete")

    state = json.loads(STATE.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_confirm_20260929_15_on_sale_four_batches",
        "last_heartbeat_at": NOW,
        "last_completed_stage": "2026-09-29 11:05开售确认与动态分组",
        "last_completed_at": NOW,
        "last_stage_status": "completed_confirm_15_on_sale_nowscore_available_no_ledger_write",
        "last_stage_artifact": REPORT,
        "confirm_source_status": "2026-09-29_1105_official_15_on_sale_four_play_fetch_ok_four_dynamic_groups_heartbeat_queue",
        "inner_outer_alignment_status": "2026-09-29_1108_primary_quota_insufficient_nowscore_mapped15_of15_research_rows192",
        "next_dynamic_task_key": "2026-09-29|14:00|终版分析",
        "next_dynamic_task_at": "2026-09-29T12:30:00+08:00",
        "next_required_stage": "2026-09-29 12:30终版001；13:00复盘2026-09-28",
        "next_required_at": "2026-09-29T12:30:00+08:00",
        "pending_reschedule": True,
        "pending_reschedule_reason": "fixed 30-minute heartbeat remains active; registry is the work queue and the next due batch is 001 at 12:30",
    })
    state["the_odds_quota_status"] = {
        "checked_at": "2026-09-29T11:08:35+08:00",
        "key_valid": True,
        "requests_used": 499,
        "requests_remaining": 1,
        "estimated_credit_cost": 12,
        "blocked": True,
        "diagnosis": "remaining quota 1 is below the estimated 12-credit routed request; no paid odds request was sent",
        "today_policy": "refresh official four-play data at every final batch; use Nowscore only as research fallback and otherwise degrade to official market baseline",
    }
    state["confirm_20260929"] = {
        "status": "completed",
        "completed_at": NOW,
        "official_captured_at": NOW,
        "fixture_count": 15,
        "on_sale": 15,
        "stopped": 0,
        "match_numbers": "001-015",
        "delta_from_preopen": "001 and 007 remained; 002-006 and 008-015 were newly published, for 15 total on-sale fixtures",
        "official_four_play_fetch": "ok",
        "the_odds": "quota_insufficient_remaining1_estimated12_mapped0_of15",
        "nowscore_fallback": "complete_mapped15_of15_quote_rows1530_asian_rows255_research_rows192_failures0",
        "effective_external_market": ext["effective_status"],
        "production_model_feature_ready": False,
        "dynamic_batches": "12:30_001;16:30_002-007;21:00_008-014;21:00_015",
        "ledger_write_performed": False,
        "registry": REGISTRY,
        "report": REPORT,
        "supabase_sync": "not_authorized_for_2026-09-29",
    }
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "on_sale": 15, "tasks": 4, "next": "2026-09-29T12:30:00+08:00"}))


if __name__ == "__main__":
    main()
