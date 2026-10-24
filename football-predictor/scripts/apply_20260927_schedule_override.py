from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-09-27T12:03:00+08:00"


def main() -> None:
    registry_path = ROOT / "artifacts/data/sporttery_task_registry_2026-09-27.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    retained = [
        task for task in registry["tasks"]
        if task["key"] not in {
            "2026-09-27|18:00|终版分析",
            "2026-09-27|19:35-20:30|终版分析",
            "2026-09-27|00:00|终版分析",
            "2026-09-27|02:45|终版分析",
            "2026-09-27|07:00|终版分析",
            "2026-09-27|15:00|全9场赔率基线",
            "2026-09-27|16:30|001-003终版",
            "2026-09-27|22:00|004-009终版",
        }
    ]
    common = {
        "sales_day": "2026-09-27", "status": "pending_schedule", "revision": 2,
        "scheduling_attempts": 0, "automation_id": None, "last_error": None,
        "created_at": NOW, "updated_at": NOW,
    }
    baseline = {
        **common,
        "key": "2026-09-27|15:00|全9场赔率基线", "time_group": "全9场",
        "purpose": "早期基线分析", "task_name": "2026-09-27|15:00|全9场赔率基线",
        "run_at": "2026-09-27T15:00:00+08:00",
        "match_numbers": ["001", "002", "003", "004", "005", "006", "007", "008", "009"],
        "matches": [
            "001 江原FC vs 仁川联", "002 中国 vs 新西兰", "003 格拉夫 vs 登博思",
            "004 丹麦 vs 威尔士", "005 塞尔维亚 vs 荷兰", "006 奥地利 vs 科索沃",
            "007 德国 vs 希腊", "008 挪威 vs 葡萄牙", "009 哥伦布 vs 迈国际",
        ],
        "external_odds_policy": "refresh_baseline_with_nowscore_fallback",
        "confirm_snapshot_status": "quota_insufficient",
        "ledger_write_forbidden": True,
    }
    first_final = {
        **common,
        "key": "2026-09-27|16:30|001-003终版", "time_group": "18:00-20:30",
        "purpose": "终版分析", "task_name": "2026-09-27|16:30|001-003终版",
        "run_at": "2026-09-27T16:30:00+08:00", "hard_lock": "2026-09-27T17:45:00+08:00",
        "sales_cutoff": "2026-09-27T18:00:00+08:00",
        "match_numbers": ["001", "002", "003"],
        "matches": ["001 江原FC vs 仁川联", "002 中国 vs 新西兰", "003 格拉夫 vs 登博思"],
        "external_odds_policy": "refresh_at_final", "confirm_snapshot_status": "quota_insufficient",
        "baseline_reference": "2026-09-27|15:00|全9场赔率基线",
    }
    late_final = {
        **common,
        "key": "2026-09-27|22:00|004-009终版", "time_group": "00:00-07:00",
        "purpose": "终版分析", "task_name": "2026-09-27|22:00|004-009终版",
        "run_at": "2026-09-27T22:00:00+08:00", "hard_lock": "2026-09-27T22:45:00+08:00",
        "sales_cutoff": "2026-09-27T23:00:00+08:00",
        "match_numbers": ["004", "005", "006", "007", "008", "009"],
        "matches": [
            "004 丹麦 vs 威尔士", "005 塞尔维亚 vs 荷兰", "006 奥地利 vs 科索沃",
            "007 德国 vs 希腊", "008 挪威 vs 葡萄牙", "009 哥伦布 vs 迈国际",
        ],
        "external_odds_policy": "refresh_at_final", "confirm_snapshot_status": "quota_insufficient",
        "baseline_reference": "2026-09-27|15:00|全9场赔率基线",
    }
    registry["tasks"] = sorted(retained + [baseline, first_final, late_final], key=lambda item: item["run_at"])
    registry["updated_at"] = NOW
    registry["schedule_override"] = "artifacts/data/sporttery_daily_schedule_override_2026-09-27.json"
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = ROOT / "artifacts/data/football_automation_controller_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "last_schedule_adjustment_at": NOW,
        "last_schedule_adjustment_artifact": "artifacts/data/sporttery_daily_schedule_override_2026-09-27.json",
        "next_dynamic_task_key": baseline["key"], "next_dynamic_task_at": baseline["run_at"],
        "next_required_stage": "2026-09-27 13:00复盘；15:00全9场赔率基线；16:30终版001-003",
        "next_required_at": "2026-09-27T13:00:00+08:00",
        "pending_reschedule": True,
        "pending_reschedule_reason": "automation_update interface unavailable; fixed heartbeat remains active and custom registry tasks remain pending_schedule",
    })
    state["today_schedule_override"] = {
        "sales_day": "2026-09-27", "requested_at": NOW,
        "artifact": "artifacts/data/sporttery_daily_schedule_override_2026-09-27.json",
        "stages": [
            "2026-09-27T13:00:00+08:00|前一销售日复盘|2026-09-26",
            "2026-09-27T15:00:00+08:00|全9场赔率基线|001-009",
            "2026-09-27T16:30:00+08:00|合并终版|001-003",
            "2026-09-27T22:00:00+08:00|晚间终版|004-009",
            "2026-09-28T13:00:00+08:00|全期复盘|001-009",
        ],
        "duplicate_ledger_write_forbidden": True,
        "gate_relaxation_allowed": False,
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "updated", "tasks": len(registry["tasks"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
