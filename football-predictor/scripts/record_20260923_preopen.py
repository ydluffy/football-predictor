from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "artifacts/data/football_automation_controller_state.json"


def main() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state.update(
        {
            "last_heartbeat_at": "2026-09-23T10:05:29+08:00",
            "last_completed_stage": "2026-09-23 10:00开售前预扫描",
            "last_completed_at": "2026-09-23T10:05:29+08:00",
            "last_stage_status": "completed_preopen_two_prelisted_001_002_no_ledger_write",
            "last_stage_artifact": "artifacts/betting/sporttery_sales_window_scan_2026-09-23_1005_preopen.md",
            "preopen_source_status": "2026-09-23_1005_official_two_prelisted_four_play_fetch_ok_requires_1105_confirmation",
            "next_dynamic_task_key": None,
            "next_dynamic_task_at": None,
            "next_required_stage": "2026-09-23 11:05在售确认；13:00复盘2026-09-22销售日",
            "next_required_at": "2026-09-23T11:05:00+08:00",
        }
    )
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "prelisted": 2, "next": "2026-09-23T11:05:00+08:00"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
