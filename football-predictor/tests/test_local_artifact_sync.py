import importlib.util
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

spec = importlib.util.spec_from_file_location(
    "local_artifact_sync",
    Path(__file__).parents[1] / "scripts/sync_local_artifacts_to_supabase.py",
)
sync = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sync
spec.loader.exec_module(sync)


def test_database_conflict_is_failure():
    response = requests.Response()
    response.status_code = 500
    response._content = b'{"error":"ON CONFLICT DO UPDATE command cannot affect row a second time"}'
    session = Mock()
    session.post.return_value = response
    result = sync.post_json(session, "http://localhost/test", {}, "test")
    assert not result.ok
    assert not result.warning


def test_non_json_response_preserved():
    response = requests.Response()
    response._content = b"upstream unavailable"
    assert sync.try_json(response) == "upstream unavailable"


def test_default_mode_returns_failure_without_strict(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["sync", "--days-back", "1"])
    monkeypatch.setattr(sys.stdout, "reconfigure", lambda **kwargs: None, raising=False)
    monkeypatch.setattr(sync, "get_json", lambda *args: sync.SyncResult("status", True, 200, {}))
    monkeypatch.setattr(sync, "post_json", lambda *args: sync.SyncResult("write", False, 500, {}))
    assert sync.main() == 1


@pytest.mark.parametrize("option", ["--batch-size", "--days-back"])
def test_invalid_counts_rejected_before_network(monkeypatch, option):
    monkeypatch.setattr(sys, "argv", ["sync", option, "0"])
    monkeypatch.setattr(sys.stdout, "reconfigure", lambda **kwargs: None, raising=False)
    with pytest.raises(SystemExit) as exc:
        sync.main()
    assert exc.value.code == 2
