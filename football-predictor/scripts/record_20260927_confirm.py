from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "artifacts/data/football_automation_controller_state.json"


def main() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_confirm_9_on_sale_five_batches_no_ledger_write",
        "last_heartbeat_at": "2026-09-27T11:06:56+08:00",
        "last_completed_stage": "2026-09-27 11:05在售确认与任务编排",
        "last_completed_at": "2026-09-27T11:12:00+08:00",
        "last_stage_status": "completed_confirm_9_on_sale_2_stopped_the_odds_quota1_nowscore_mapped9_no_ledger_write",
        "last_stage_artifact": "artifacts/betting/sporttery_sales_window_scan_2026-09-27_1106_confirm.md",
        "confirm_source_status": "2026-09-27_1106_official_9_on_sale_2_stopped_four_play_fetch_ok_five_dynamic_groups_heartbeat_queue",
        "inner_outer_alignment_status": "2026-09-27_1108_primary_quota_insufficient_remaining1_nowscore_complete_mapped9_of9_research_rows124_production_feature_not_ready",
        "next_dynamic_task_key": "2026-09-27|18:00|终版分析",
        "next_dynamic_task_at": "2026-09-27T16:30:00+08:00",
        "next_required_stage": "2026-09-27 13:00复盘2026-09-26销售日；16:30终版分析001",
        "next_required_at": "2026-09-27T13:00:00+08:00",
        "pending_reschedule": True,
        "pending_reschedule_reason": "automation_update interface unavailable; fixed heartbeat remains active and registry tasks remain pending_schedule",
        "the_odds_quota_status": {
            "checked_at": "2026-09-27T11:08:28+08:00",
            "key_valid": True,
            "requests_used": 499,
            "requests_remaining": 1,
            "estimated_credit_cost": 24,
            "blocked": True,
            "diagnosis": "当前自然月额度仅余1，低于本次两条赛事路由预计24 credits；未发起付费赔率请求。",
            "today_policy": "正式批次继续尝试捷报后备；若失败则明确降级为体彩市场基线。",
        },
        "football_data_europe_incremental_status": {
            "checked_at": "2026-09-27T11:12:00+08:00",
            "status": "ok", "date_from": "2026-09-26", "date_to": "2026-09-28",
            "matches": 0, "standings": 132,
            "note": "当前在售场次不属于七联赛覆盖范围；积分历史已正常刷新。",
        },
    })
    state["confirm_20260927"] = {
        "status": "completed", "completed_at": "2026-09-27T11:12:00+08:00",
        "fixture_count": 11, "on_sale": 9, "stopped": 2,
        "match_numbers_on_sale": ["001", "002", "003", "004", "005", "006", "007", "008", "009"],
        "stopped_match_numbers": ["024", "025"],
        "delta_from_preopen": "024/025 stopped after kickoff; 002/004/005/006/007/008 newly visible; 001/003/009 confirmed on_sale",
        "official_four_play_fetch": "ok",
        "the_odds": "quota_insufficient_remaining1_estimated24_mapped0_of9",
        "nowscore_fallback": "complete_mapped9_of9_quote_rows918_asian_rows153_research_rows124_failures0",
        "effective_external_market": "available_via_nowscore_production_model_feature_not_ready",
        "dynamic_batches": "16:30_001;18:05_002-003;22:00_004-009",
        "ledger_write_performed": False,
        "registry": "artifacts/data/sporttery_task_registry_2026-09-27.json",
        "report": "artifacts/betting/sporttery_sales_window_scan_2026-09-27_1106_confirm.md",
        "supabase_sync": "not_authorized_for_2026-09-27",
    }
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "on_sale": 9, "stopped": 2, "next": "2026-09-27T13:00:00+08:00"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
