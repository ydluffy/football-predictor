from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-27T15:12:00+08:00"
TASK_KEY = "2026-09-27|15:00|全9场赔率基线"
REPORT = "artifacts/betting/sporttery_early_baseline_2026-09-27_1506_001-009.md"
AUDIT = "artifacts/data/sporttery_early_baseline_2026-09-27_1506_001-009.json"


def main() -> None:
    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-27.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    matches = [task for task in registry["tasks"] if task["key"] == TASK_KEY]
    if len(matches) != 1:
        raise ValueError(f"expected one baseline task, found {len(matches)}")
    matches[0].update({
        "status": "completed",
        "updated_at": NOW,
        "completed_at": NOW,
        "completion_status": "completed_9_match_official_and_nowscore_baseline_no_ledger",
        "artifact": AUDIT,
        "report": REPORT,
        "official_on_sale": 9,
        "nowscore_mapped": 9,
        "production_ledger_write_performed": False,
    })
    registry["updated_at"] = NOW
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "status": "completed_early_baseline_9_no_ledger_write",
        "last_heartbeat_at": "2026-09-27T15:06:00+08:00",
        "last_completed_stage": "2026-09-27 15:00全9场赔率基线",
        "last_completed_at": NOW,
        "last_stage_status": "completed_9_match_official_and_nowscore_baseline_no_ledger",
        "last_stage_artifact": REPORT,
        "inner_outer_alignment_status": "2026-09-27_1506_primary_quota_insufficient_nowscore_mapped9_of9_research_rows125",  # pragma: allowlist secret - non-secret status or character set
        "next_required_stage": "2026-09-27 16:30终版分析001-003",
        "next_required_at": "2026-09-27T16:30:00+08:00",
        "next_dynamic_task_key": "2026-09-27|16:30|001-003终版",
        "next_dynamic_task_at": "2026-09-27T16:30:00+08:00",
        "pending_reschedule": True,
        "pending_reschedule_reason": "automation_update interface unavailable; fixed heartbeat remains active and custom registry tasks remain pending_schedule",
    })
    state["baseline_20260927_1500"] = {
        "status": "completed",
        "completed_at": NOW,
        "official_captured_at": "2026-09-27T15:06:00+08:00",
        "fixture_count": 9,
        "match_numbers": "001-009",
        "excluded_stopped_match_numbers": ["024", "025"],
        "official_four_play_fetch": "ok",
        "the_odds": "quota_insufficient_remaining1_estimated24",
        "nowscore_fallback": "complete_mapped9_of9_research_rows125_failures0",
        "production_model_feature_ready": False,
        "production_ledger_write_performed": False,
        "report": REPORT,
        "audit": AUDIT,
        "supabase_sync": "not_authorized_for_2026-09-27",
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "task": TASK_KEY, "next": state["next_dynamic_task_key"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
