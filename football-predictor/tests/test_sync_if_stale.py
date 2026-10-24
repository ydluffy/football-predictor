import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location("sync_if_stale", Path(__file__).parents[1] / "scripts/sync_if_stale.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

DAY = "2026-10-24"
# 判定是相对时间比较，测试必须锚在真实当前时刻，不能用固定的历史时刻。
NOW = datetime.now(timezone(timedelta(hours=8)))


def isolate_latest_aliases(monkeypatch, tmp_path):
    """两个 latest 别名指向仓库真实路径，测试必须切断，否则判定会被真实仓库状态污染。"""
    monkeypatch.setattr(guard, "MOVEMENT_CSV", tmp_path / "absent_movement.csv")
    monkeypatch.setattr(guard, "ALIGNMENT_CSV", tmp_path / "absent_alignment.csv")


def artifact(tmp_path, name="sporttery_task_registry_2026-10-24.json", age_seconds=600):
    path = tmp_path / "artifacts/data" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))
    return path


def synced_state(stage="confirm", pushed_at=NOW):
    state = {"jobs": {}}
    for step in guard.STAGES[stage]:
        state["jobs"][f"{DAY}|{step}"] = {"status": "completed", "last_attempt_at": pushed_at.isoformat()}
    return state


def test_unchanged_artifacts_are_up_to_date(tmp_path, monkeypatch):
    isolate_latest_aliases(monkeypatch, tmp_path)
    artifact(tmp_path)
    pending, reasons = guard.decide(synced_state(), [DAY], "confirm", tmp_path)
    assert pending == [] and reasons[DAY] == "up_to_date"


def test_artifacts_changed_after_the_last_push_are_stale(tmp_path, monkeypatch):
    isolate_latest_aliases(monkeypatch, tmp_path)
    artifact(tmp_path, age_seconds=0)  # 本批刚写完的产物
    pending, reasons = guard.decide(synced_state(pushed_at=NOW - timedelta(hours=3)), [DAY], "confirm", tmp_path)
    assert pending == [DAY] and reasons[DAY] == "artifacts_newer"


def test_day_that_was_never_fully_synced_is_stale(tmp_path, monkeypatch):
    isolate_latest_aliases(monkeypatch, tmp_path)
    artifact(tmp_path)
    pending, reasons = guard.decide({"jobs": {}}, [DAY], "confirm", tmp_path)
    assert pending == [DAY] and reasons[DAY] == "never_fully_synced"


def test_one_missing_step_is_enough_to_retry(tmp_path, monkeypatch):
    isolate_latest_aliases(monkeypatch, tmp_path)
    artifact(tmp_path)
    state = synced_state()
    del state["jobs"][f"{DAY}|market"]
    pending, reasons = guard.decide(state, [DAY], "confirm", tmp_path)
    assert pending == [DAY] and reasons[DAY] == "never_fully_synced"


def test_day_without_local_artifacts_is_skipped_without_a_request(tmp_path, monkeypatch):
    isolate_latest_aliases(monkeypatch, tmp_path)
    pending, reasons = guard.decide(synced_state(), ["1999-01-01"], "confirm", tmp_path)
    assert pending == [] and reasons["1999-01-01"] == "no_local_artifact"


def test_a_completed_stage_does_not_stand_in_for_another_stage(tmp_path, monkeypatch):
    isolate_latest_aliases(monkeypatch, tmp_path)
    artifact(tmp_path, age_seconds=600)
    # confirm 已全部成功，但 review 需要的是 history/controller，缺 history 就必须补同步。
    pending, reasons = guard.decide(synced_state("confirm"), [DAY], "review", tmp_path)
    assert pending == [DAY] and reasons[DAY] == "never_fully_synced"
    assert guard.decide(synced_state("review"), [DAY], "review", tmp_path)[0] == []


def test_sync_command_passes_day_and_stage_to_the_existing_sync_entry(tmp_path):
    command = guard.sync_command([DAY], "confirm", "http://127.0.0.1:3100", tmp_path)
    assert command[1] == str(guard.SYNC_SCRIPT)
    assert command[2:] == ["--stage", "confirm", "--base-url", "http://127.0.0.1:3100",
                           "--sales-day", DAY, "--state-dir", str(tmp_path)]


def test_default_state_dir_is_not_passed_twice():
    command = guard.sync_command([DAY], "confirm", guard.DEFAULT_BASE_URL, guard.STATE_DIR)
    assert "--state-dir" not in command


def test_main_prints_up_to_date_without_delegating(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", ["guard", "--sales-day", DAY, "--stage", "confirm", "--state-dir", str(tmp_path)])
    monkeypatch.setattr(guard, "decide", lambda state, days, stage: ([], {DAY: "up_to_date"}))
    monkeypatch.setattr(guard.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not sync")))
    assert guard.main() == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "up_to_date"


def test_main_delegates_only_the_stale_days(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["guard", "--sales-day", DAY, "--stage", "confirm", "--state-dir", str(tmp_path)])
    monkeypatch.setattr(guard, "decide", lambda state, days, stage: ([DAY], {DAY: "artifacts_newer"}))

    class Result:
        returncode = 0

    calls = []
    monkeypatch.setattr(guard.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)) or Result())
    assert guard.main() == 0
    command, kwargs = calls[0]
    assert command[2:] == ["--stage", "confirm", "--base-url", guard.DEFAULT_BASE_URL,
                           "--sales-day", DAY, "--state-dir", str(tmp_path)]
    assert kwargs["cwd"] == str(guard.ROOT)
