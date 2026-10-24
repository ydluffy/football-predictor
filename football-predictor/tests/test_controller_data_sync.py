import importlib.util
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import requests

spec = importlib.util.spec_from_file_location("controller_sync", Path(__file__).parents[1] / "scripts/run_controller_data_sync.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)
NOW = datetime.fromisoformat("2026-09-04T18:15:00+08:00")


def response(status=200, verified=True):
    result = Mock(ok=status == 200, status_code=status)
    result.json.return_value = {"verified": verified}
    return result


def test_stage_scopes_and_duplicate_days():
    state = {"jobs": {}}
    sync.enqueue(state, ["2026-09-03", "2026-09-03"], "review", NOW)
    assert set(state["jobs"]) == {"2026-09-03|history", "2026-09-03|controller"}


def test_200_without_database_verification_is_not_success():
    session = Mock()
    session.post.return_value = response(200, False)
    assert not sync.attempt(session, "http://localhost", {"step": "snapshot", "sales_day": "2026-09-04"})["ok"]
    assert session.post.call_count == 1


def test_connection_failure_is_bounded_and_remains_pending():
    state = {"jobs": {}}
    sync.enqueue(state, ["2026-09-04"], "controller", NOW)
    session = Mock()
    session.post.side_effect = requests.ConnectionError("do not expose connection secrets")
    persist = Mock()
    result = sync.run_pending(state, session, "http://localhost", NOW, persist)
    assert session.post.call_count == 2
    assert state["jobs"]["2026-09-04|controller"]["status"] == "pending"
    assert "secrets" not in str(result)
    persist.assert_called_once()


def test_only_pending_steps_retried_and_success_clears_them(monkeypatch, tmp_path):
    # CI has no production ledgers; exercise the real exporter with isolated inputs.
    folder = tmp_path / "data/manual"
    folder.mkdir(parents=True)
    for name in ("betting_plan_ledger.csv", "fixed_odds_shadow_ledger.csv"):
        (folder / name).write_text("date,plan_id,result,stake,payout,net_profit,roi,selections\n", encoding="utf-8")
    export = sync.frozen_review_export
    monkeypatch.setattr(sync, "frozen_review_export", lambda day: export(day, tmp_path))
    monkeypatch.setattr(sync, "market_artifact_coverage", lambda day: {"newest_day": {}, "stale": []})
    state = {"jobs": {}}
    sync.enqueue(state, ["2026-09-04"], "analysis", NOW)
    state["jobs"]["2026-09-04|snapshot"]["status"] = "completed"
    session = Mock()
    session.post.return_value = response()
    sync.run_pending(state, session, "http://localhost", NOW, Mock())
    assert session.post.call_count == len(sync.STAGES["analysis"]) - 1
    assert all(j["status"] == "completed" for j in state["jobs"].values())


def test_missing_ledgers_block_history_without_network(monkeypatch, tmp_path):
    export = sync.frozen_review_export
    monkeypatch.setattr(sync, "frozen_review_export", lambda day: export(day, tmp_path))
    session = Mock()
    result = sync.attempt(session, "http://localhost", {"step": "history", "sales_day": "2026-09-04"})
    assert result["reason"] == "invalid_local_ledger_export"
    assert result["ok"] is False
    session.post.assert_not_called()


def test_auth_failure_not_retried_immediately():
    session = Mock()
    session.post.return_value = response(401, False)
    sync.attempt(session, "http://localhost", {"step": "controller", "sales_day": "2026-09-04"})
    assert session.post.call_count == 1


def test_dry_run_has_no_writes_or_network(monkeypatch, tmp_path):
    import sys
    monkeypatch.setattr(sys, "argv", ["sync", "--sales-day", "2026-09-04", "--stage", "confirm", "--dry-run", "--state-dir", str(tmp_path / "outbox")])
    monkeypatch.setattr(sync.requests, "Session", lambda: (_ for _ in ()).throw(AssertionError("network")))
    assert sync.main() == 0
    assert not (tmp_path / "outbox").exists()


def test_cooldown_and_batch_limit(monkeypatch):
    monkeypatch.setattr(sync, "market_artifact_coverage", lambda day: {"newest_day": {}, "stale": []})
    state = {"jobs": {}}
    sync.enqueue(state, ["2026-09-04"], "analysis", NOW)
    session = Mock()
    session.post.return_value = response()
    sync.run_pending(state, session, "http://localhost", NOW, Mock(), max_jobs=1)
    assert session.post.call_count == 1
    state["jobs"]["2026-09-04|history"]["next_retry_at"] = "2026-09-05T18:15:00+08:00"
    sync.run_pending(state, session, "http://localhost", NOW, Mock())
    assert state["jobs"]["2026-09-04|history"]["status"] == "pending"


def test_credentials_loaded_without_optional_dependencies(tmp_path, monkeypatch):
    path = tmp_path / ".env.local"
    path.write_text('WORKBENCH_ADMIN_USER="local"\nWORKBENCH_ADMIN_PASSWORD=\'p#q\'\nSUPABASE_SERVICE_ROLE_KEY=excluded\n', encoding="utf-8")
    monkeypatch.setenv("WORKBENCH_ADMIN_USER", "override")
    monkeypatch.delenv("WORKBENCH_ADMIN_PASSWORD", raising=False)
    assert sync.admin_credentials(path) == {"WORKBENCH_ADMIN_USER": "override", "WORKBENCH_ADMIN_PASSWORD": "p#q"}  # pragma: allowlist secret - test fixture


def test_frozen_ledger_export_does_not_mutate_or_recalculate(tmp_path):
    folder = tmp_path / "data/manual"
    folder.mkdir(parents=True)
    header = "date,plan_id,result,stake,payout,net_profit,roi,selections\n"
    real = folder / "betting_plan_ledger.csv"
    shadow = folder / "fixed_odds_shadow_ledger.csv"
    text = header + "2026-09-03,SAFE,命中,100,199.5,99.5,0.995,003客胜\n"
    real.write_text(text, encoding="utf-8")
    shadow.write_text(header, encoding="utf-8")
    result = sync.frozen_review_export("2026-09-03", tmp_path)
    assert result["real_summary"]["net_profit"] == 99.5
    assert result["reviewed_at"] is None
    assert real.read_text(encoding="utf-8") == text
    assert len(result["source_sha256"]) == 2


def test_market_payload_uses_latest_nowscore_price_changes(tmp_path, monkeypatch):
    root = tmp_path / "snapshots"
    older = root / "2026-09-04_20260904T100000000000Z"
    newer = root / "2026-09-04_20260904T120000000000Z"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    header = "odds_id,changed_at_raw,handicap_raw,home_price_raw,away_price_raw,handicap,is_opening\n"
    (older / "price_changes.csv").write_text(header, encoding="utf-8")
    (newer / "price_changes.csv").write_text(
        header
        + "17841227,10-19 17:56初,平手/半球,0.88,0.96,-0.25,True\n"
        + ",10-19 17:56初,平手/半球,0.88,0.96,-0.25,True\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sync, "NOWSCORE_SNAPSHOT_ROOT", root)
    monkeypatch.setattr(sync, "MOVEMENT_CSV", tmp_path / "absent_movement.csv")
    monkeypatch.setattr(sync, "ALIGNMENT_CSV", tmp_path / "absent_alignment.csv")
    rows = sync.price_change_rows("2026-09-04")
    assert [row["odds_id"] for row in rows] == ["17841227"]
    assert rows[0]["handicap"] == "-0.25"
    assert sync.market_payload("2026-09-04")["price_change_rows"] == rows
    monkeypatch.setattr(sync, "NOWSCORE_SNAPSHOT_ROOT", tmp_path / "absent")
    assert sync.market_payload("2026-09-04")["price_change_rows"] == []


def test_duplicate_ledger_identity_rejected(tmp_path):
    import pytest
    folder = tmp_path / "data/manual"
    folder.mkdir(parents=True)
    row = "2026-09-03,SAME,待结算,100,,,,A\n"
    (folder / "betting_plan_ledger.csv").write_text("date,plan_id,result,stake,payout,net_profit,roi,selections\n" + row + row, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate_or_missing_plan_id"):
        sync.frozen_review_export("2026-09-03", tmp_path)


def test_market_payload_ships_only_the_requested_sales_day(tmp_path, monkeypatch):
    movement = tmp_path / "movement.csv"
    movement.write_text("match_id,home_team\n2026-09-04|001,A\n2026-09-03|002,B\n", encoding="utf-8")
    alignment = tmp_path / "alignment.csv"
    alignment.write_text(
        "match_id,sales_day,home_team\n"
        + "2026-09-04|001,2026-09-04,A\n"
        + "2026-09-03|002,2026-09-03,B\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sync, "MOVEMENT_CSV", movement)
    monkeypatch.setattr(sync, "ALIGNMENT_CSV", alignment)
    monkeypatch.setattr(sync, "NOWSCORE_SNAPSHOT_ROOT", tmp_path / "absent")
    payload = sync.market_payload("2026-09-04")
    assert [row["match_id"] for row in payload["movement_rows"]] == ["2026-09-04|001"]
    assert [row["match_id"] for row in payload["alignment_rows"]] == ["2026-09-04|001"]


def test_stale_market_artifact_is_rejected_without_a_request(tmp_path, monkeypatch):
    movement = tmp_path / "movement.csv"
    movement.write_text("match_id,home_team\n2026-08-16|001,A\n", encoding="utf-8")
    alignment = tmp_path / "alignment.csv"
    alignment.write_text("match_id,sales_day\n2026-08-17|001,2026-08-17\n", encoding="utf-8")
    monkeypatch.setattr(sync, "MOVEMENT_CSV", movement)
    monkeypatch.setattr(sync, "ALIGNMENT_CSV", alignment)
    session = Mock()
    result = sync.attempt(session, "http://localhost", {"step": "market", "sales_day": "2026-09-04"})
    assert not result["ok"] and result["reason"] == "stale_local_artifact"
    assert set(result["stale_artifacts"]) == {"movement", "alignment"}
    assert result["request_attempts"] == 0
    assert session.post.call_count == 0


def test_market_rows_matching_no_fixture_are_not_a_success(monkeypatch):
    monkeypatch.setattr(sync, "market_artifact_coverage", lambda day: {"newest_day": {}, "stale": []})
    monkeypatch.setattr(sync, "market_payload", lambda day: {"sales_day": day})
    payload = Mock(ok=True, status_code=200)
    payload.json.return_value = {"verified": True, "fixture_count": 13, "persisted_market_intel": 0,
                                 "movement_rows_received": 9, "matched_movement": 0,
                                 "alignment_rows_received": 9, "matched_alignment": 0}
    session = Mock()
    session.post.return_value = payload
    result = sync.attempt(session, "http://localhost", {"step": "market", "sales_day": "2026-09-04"})
    assert not result["ok"] and result["reason"] == "market_rows_unmatched"
    assert result["counts"]["movement_rows_received"] == 9
    assert session.post.call_count == 1


def test_rebuild_market_artifacts_runs_both_builders():
    calls = []
    sync.rebuild_market_artifacts(runner=lambda command, **kwargs: calls.append((command, kwargs)))
    assert [command[1] for command, _ in calls] == [str(sync.ROOT / name) for name in sync.MARKET_ARTIFACT_BUILDERS]
    assert all(kwargs["check"] is True and kwargs["cwd"] == str(sync.ROOT) for _, kwargs in calls)


def test_rebuild_market_needs_a_stage_containing_market(monkeypatch, tmp_path):
    import sys
    import pytest
    monkeypatch.setattr(sys, "argv", ["sync", "--sales-day", "2026-09-04", "--stage", "review",
                                      "--rebuild-market", "--state-dir", str(tmp_path / "outbox")])
    with pytest.raises(SystemExit):
        sync.main()
    assert not (tmp_path / "outbox").exists()


def test_web_autostart_reuses_a_running_service_without_starting_or_stopping_it():
    spawn, build = Mock(), Mock()
    ready, process, actions = sync.ensure_web_service(
        "http://127.0.0.1:3000", 3000, Path("unused.log"),
        probe=lambda url: True, build=build, spawn=spawn)
    assert ready and process is None and actions == []
    build.assert_not_called()
    spawn.assert_not_called()


def test_web_autostart_only_reclaims_the_instance_it_started(tmp_path):
    probes = iter([False, False, True])
    process = Mock()
    process.poll.return_value = None  # 服务仍在运行，才轮到本进程回收
    spawned = []
    ready, handle, actions = sync.ensure_web_service(
        "http://127.0.0.1:3107", 3107, tmp_path / "web.log", timeout=5,
        probe=lambda url: next(probes), build=lambda: True,
        spawn=lambda port, log: (spawned.append((port, log)), process)[1],
        sleeper=lambda seconds: None)
    assert ready and handle is process
    assert actions == ["rebuilt_web", "started_web:3107"]
    assert [port for port, _ in spawned] == [3107]
    sync.stop_web_service(process)
    process.terminate.assert_called_once()


def test_web_autostart_timeout_does_not_claim_success(tmp_path):
    process = Mock()
    process.poll.return_value = None
    ready, handle, actions = sync.ensure_web_service(
        "http://127.0.0.1:3000", 3000, tmp_path / "web.log", timeout=0,
        probe=lambda url: False, build=lambda: False, spawn=lambda port, log: process,
        sleeper=lambda seconds: None)
    assert not ready and handle is None
    assert actions[-1] == "web_start_timeout"  # 队列保持待同步，不谎报已更新
    process.terminate.assert_called_once()


def test_health_report_failure_never_changes_the_sync_outcome():
    session = Mock()
    session.post.side_effect = requests.ConnectionError("health endpoint unreachable")
    assert sync.report_health(session, "http://localhost", {"at": "2026-09-04T18:15:00+08:00"}) is False


def test_health_snapshot_marks_pending_and_last_failure():
    results = [{"key": "2026-09-04|market", "step": "market", "ok": False, "http_status": 200,
                "reason": "market_rows_unmatched", "request_attempts": 1}]
    snapshot = sync.health_snapshot(NOW, "confirm", ["2026-09-04"], results, ["2026-09-04|market"], ["started_web:3000"])
    assert snapshot["ok"] is False and snapshot["pending_count"] == 1
    assert snapshot["last_failure_reason"] == "market_rows_unmatched"
    assert snapshot["web_started_by_sync"] is True
