"""Independent post-import audit: does not change acquisition or prediction decisions."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def audit_after_collection(root: Path, audit_path: Path) -> dict:
    try:
        digest = hashlib.sha256(audit_path.read_bytes()).hexdigest()
        event_id = f"{audit_path.resolve()}:{digest}"
        completed = subprocess.run(
            [sys.executable, str(root / "scripts/manage_research_schedule.py"),
             "after-collection", "--event-id", event_id],
            cwd=root, capture_output=True, text=True, encoding="utf-8",
            timeout=1250, check=False,
        )
        if completed.returncode:
            return {"status": "failed", "returncode": completed.returncode,
                    "detail": completed.stderr[-2000:]}
        result = json.loads(completed.stdout)
        states = {task["status"] for task in result["event_tasks"]}
        status = "failed" if "failed" in states else (
            "completed" if states == {"succeeded"} else "pending_or_paused")
        return {"status": status,
                "event_id": event_id, "result": result}
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        return {"status": "failed", "detail": str(exc)}
