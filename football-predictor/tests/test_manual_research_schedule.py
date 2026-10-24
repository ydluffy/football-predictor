from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from research_director.manual_schedule import ScheduleStore, timestamp

NOW = "2026-09-28T12:00:00+08:00"
DUE = "2026-09-28T13:30:00+08:00"
LATER = "2026-09-28T18:30:00+08:00"


@pytest.fixture
def store(tmp_path):
    instance = ScheduleStore(tmp_path / "schedule.sqlite3")
    instance.plan("audit", "coverage_audit", DUE, NOW)
    return instance


def test_manual_override_survives_replan(store):
    receipt = store.command("c1", "audit", "reschedule", 1, NOW, at=LATER)
    store.plan("audit", "coverage_audit", DUE, NOW)
    assert store.inspect(NOW)["next_due_at"] == LATER
    assert receipt["status"] == "committed_local"
    assert store.claim(DUE) is None


def test_idempotency_and_conflicting_request(store):
    first = store.command("c1", "audit", "pause", 1, NOW)
    assert store.command("c1", "audit", "pause", 1, DUE) == first
    with pytest.raises(ValueError, match="不同请求"):
        store.command("c1", "audit", "cancel", 1, NOW)


def test_pause_until_and_restart(store):
    store.command("p", "audit", "pause", 1, NOW, until=LATER)
    restarted = ScheduleStore(store.path)
    assert restarted.inspect(NOW)["next_due_at"] == LATER
    assert restarted.claim(DUE) is None
    assert restarted.claim(LATER)["status"] == "running"


def test_cancel_not_revived_by_scan(store):
    store.command("c", "audit", "cancel", 1, NOW)
    store.plan("audit", "coverage_audit", LATER, NOW)
    assert store.claim(LATER) is None
    assert store.inspect(NOW)["next_due_at"] is None


def test_resume_and_revert(store):
    store.command("p", "audit", "pause", 1, NOW)
    store.command("r", "audit", "resume", 2, NOW)
    assert store.inspect(NOW)["tasks"][0]["status"] == "pending"
    store.command("undo", "audit", "revert", 3, NOW, reference="r")
    assert store.inspect(NOW)["tasks"][0]["status"] == "paused"


def test_stale_revision_and_old_revert_rejected(store):
    store.command("p", "audit", "pause", 1, NOW)
    with pytest.raises(ValueError, match="版本冲突"):
        store.command("r", "audit", "resume", 1, NOW)
    store.command("r", "audit", "resume", 2, NOW)
    with pytest.raises(ValueError, match="最新"):
        store.command("undo", "audit", "revert", 3, NOW, reference="p")


def test_concurrent_workers_claim_once(store):
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: store.claim(DUE), range(2)))
    assert sum(c is not None for c in claims) == 1


def test_running_commands_rejected_and_success_not_replayed(store):
    task = store.claim(DUE)
    with pytest.raises(ValueError, match="正在执行"):
        store.command("p", "audit", "pause", task["revision"], DUE)
    store.finish("audit", task["revision"], DUE, result={"ok": True})
    store.plan("audit", "coverage_audit", LATER, NOW)
    assert store.claim(LATER) is None
    with pytest.raises(ValueError, match="租约"):
        store.finish("audit", task["revision"], DUE)


def test_failure_explicit_retry_preserves_attempt_history(store):
    task = store.claim(DUE)
    failed = store.finish("audit", task["revision"], DUE, error="missing input")
    assert store.claim(LATER) is None
    store.command("retry", "audit", "run_once", failed["revision"], LATER)
    retry = store.claim(LATER)
    assert retry["attempt"] == 2
    store.finish("audit", retry["revision"], LATER, result={"ok": True})
    assert {r["status"] for r in store.inspect(LATER)["runs"]} == {"failed", "succeeded"}


def test_lease_expiry_never_replays_without_review(store):
    old = store.claim(DUE)
    with pytest.raises(ValueError, match="租约"):
        store.finish("audit", old["revision"], LATER)
    assert store.claim(LATER) is None
    assert store.inspect(LATER)["tasks"][0]["status"] == "failed"
    with pytest.raises(ValueError, match="租约"):
        store.finish("audit", old["revision"], LATER)


def test_empty_queue_and_crossday_timezone(tmp_path):
    store = ScheduleStore(tmp_path / "empty.sqlite3")
    assert store.inspect(NOW)["next_due_at"] is None
    store.plan("next", "coverage_audit", "2026-09-28T17:00:00+00:00", NOW)
    assert store.inspect(NOW)["next_due_at"] == "2026-09-29T01:00:00+08:00"
    assert store.claim("2026-09-29T00:59:00+08:00") is None


def test_whitelist_naive_time_and_past_reschedule_rejected(store):
    with pytest.raises(ValueError, match="白名单"):
        store.plan("bad", "betting_plan", DUE, NOW)
    with pytest.raises(ValueError, match="时区"):
        timestamp(datetime(2026, 9, 28))
    with pytest.raises(ValueError, match="未来"):
        store.command("past", "audit", "reschedule", 1, DUE, at=NOW)


def test_revert_cannot_undo_execution(store):
    store.command("change", "audit", "reschedule", 1, NOW, at=LATER)
    task = store.claim(LATER)
    done = store.finish("audit", task["revision"], LATER, result={"ok": True})
    with pytest.raises(ValueError, match="最新"):
        store.command("undo", "audit", "revert", done["revision"], LATER,
                      reference="change")


def test_default_migration_preserves_manual_and_completed(store):
    changed = store.plan("audit", "coverage_audit", LATER, NOW, update_default=True)
    assert changed["revision"] == 2
    store.command("manual", "audit", "reschedule", 2, NOW, at=DUE)
    store.plan("audit", "coverage_audit", LATER, NOW, update_default=True)
    assert store.inspect(NOW)["next_due_at"] == DUE
    task = store.claim(DUE)
    store.finish("audit", task["revision"], DUE)
    store.plan("audit", "coverage_audit", LATER, NOW, update_default=True)
    assert store.claim(LATER) is None


def test_claim_filter_does_not_run_other_due_work(store):
    store.plan("event", "intelligence_validation", DUE, NOW)
    assert store.claim(DUE, task_ids={"event"})["id"] == "event"
    assert store.claim(DUE, task_ids={"event"}) is None
    assert store.claim(DUE)["id"] == "audit"
