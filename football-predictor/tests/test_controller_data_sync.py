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


def test_only_pending_steps_retried_and_success_clears_them():
    state = {"jobs": {}}
    sync.enqueue(state, ["2026-09-04"], "analysis", NOW)
    state["jobs"]["2026-09-04|snapshot"]["status"] = "completed"
    session = Mock()
    session.post.return_value = response()
    sync.run_pending(state, session, "http://localhost", NOW, Mock())
    assert session.post.call_count == 2
    assert all(j["status"] == "completed" for j in state["jobs"].values())


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


def test_cooldown_and_batch_limit():
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
    assert sync.admin_credentials(path) == {"WORKBENCH_ADMIN_USER": "override", "WORKBENCH_ADMIN_PASSWORD": "p#q"}


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


def test_duplicate_ledger_identity_rejected(tmp_path):
    import pytest
    folder = tmp_path / "data/manual"
    folder.mkdir(parents=True)
    row = "2026-09-03,SAME,待结算,100,,,,A\n"
    (folder / "betting_plan_ledger.csv").write_text("date,plan_id,result,stake,payout,net_profit,roi,selections\n" + row + row, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate_or_missing_plan_id"):
        sync.frozen_review_export("2026-09-03", tmp_path)
