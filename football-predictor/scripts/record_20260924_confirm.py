from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "artifacts/data/football_automation_controller_state.json"


def main() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state.update(
        {
            "status": "completed_confirm_8_on_sale_two_batches_no_ledger_write",
            "last_heartbeat_at": "2026-09-24T11:06:25+08:00",
            "last_completed_stage": "2026-09-24 11:05在售确认与任务编排",
            "last_completed_at": "2026-09-24T12:34:00+08:00",
            "last_stage_status": "completed_confirm_refresh_8_on_sale_the_odds_quota1_nowscore_mapped8_no_ledger_write",
            "last_stage_artifact": "artifacts/betting/sporttery_sales_window_scan_2026-09-24_1232_confirm.md",
            "confirm_source_status": "2026-09-24_1232_official_8_on_sale_all_before_kickoff_four_play_fetch_ok_two_dynamic_groups_heartbeat_queue",
            "inner_outer_alignment_status": "2026-09-24_1232_primary_quota_insufficient_remaining1_nowscore_complete_mapped8_of8_research_rows96_production_feature_not_ready",
            "next_dynamic_task_key": "2026-09-24|18:05-19:35|终版分析",
            "next_dynamic_task_at": "2026-09-24T16:35:00+08:00",
            "next_required_stage": "2026-09-24 13:00复盘2026-09-23销售日；16:35终版分析001-003",
            "next_required_at": "2026-09-24T13:00:00+08:00",
            "the_odds_quota_status": {
                "checked_at": "2026-09-24T11:08:47+08:00",
                "key_valid": True,
                "requests_used": 499,
                "requests_remaining": 1,
                "estimated_credit_cost": 12,
                "blocked": True,
                "diagnosis": "当前自然月额度仅余1，低于本次欧国联路由预计12 credits；未发起付费赔率请求。",
                "today_policy": "正式批次继续尝试捷报后备；若仍失败则明确降级为体彩市场基线。",
            },
            "football_data_europe_incremental_status": {
                "checked_at": "2026-09-24T11:09:00+08:00",
                "status": "ok",
                "date_from": "2026-09-23",
                "date_to": "2026-09-25",
                "matches": 0,
                "standings": 132,
                "note": "今日8场为国家队赛事，不在七联赛赛程范围；积分历史已正常刷新。",
            },
        }
    )
    state["confirm_20260924"] = {
        "status": "completed",
        "completed_at": "2026-09-24T12:34:00+08:00",
        "fixture_count": 8,
        "on_sale": 8,
        "stopped": 0,
        "match_numbers": "001-008",
        "delta_from_preopen": "unchanged; all 8 prelisted fixtures confirmed on_sale",
        "official_four_play_fetch": "ok",
        "the_odds": "quota_insufficient_remaining1_estimated12_mapped0_of8",
        "nowscore_fallback": "complete_mapped8_of8_quote_rows816_asian_rows136_research_rows96_failures0",
        "effective_external_market": "available_via_nowscore_production_model_feature_not_ready",
        "dynamic_batches": "16:35_001-003;21:00_004-008",
        "ledger_write_performed": False,
        "registry": "artifacts/data/sporttery_task_registry_2026-09-24.json",
        "report": "artifacts/betting/sporttery_sales_window_scan_2026-09-24_1232_confirm.md",
        "supabase_sync": "not_authorized_for_2026-09-24",
    }
    state["nowscore_parser_repair_20260924"] = {
        "status": "completed_and_live_verified",
        "completed_at": "2026-09-24T12:34:00+08:00",
        "cause": "page-level first date was assigned to every match row on multi-sales-day pages",
        "fix": "each row now inherits the nearest preceding sales-day heading; target day must exist among parsed row days",
        "cache_controls": "request sends Cache-Control and Pragma no-cache",
        "tests": "8 passed",
        "live_cp_sales_days": ["2026-09-23", "2026-09-24"],
        "live_mapped": 8,
        "live_captured": 8,
        "live_quote_rows": 816,
        "live_asian_rows": 136,
        "live_research_eligible_rows": 96,
        "live_failures": 0,
        "unified_history": "complete",
    }
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "on_sale": 8, "next": "2026-09-24T13:00:00+08:00"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
