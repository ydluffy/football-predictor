import hashlib
import json

import pytest

from data.entity_archive import connect, ingest, report


def archive(tmp_path, rows, label="fixtures_2026-10-22"):
    content = json.dumps({"response": rows}).encode()
    path = tmp_path / ("20261021T130937Z_" + label + "_" + hashlib.sha256(content).hexdigest()[:12] + ".json")
    path.write_bytes(content)
    return str(path)


def fixture():
    return {"fixture": {"id": 1, "date": "2026-10-22T00:00:00Z"},
            "league": {"id": 2, "name": "League", "season": 2026},
            "teams": {"home": {"id": 10, "name": "Same name"},
                      "away": {"id": 11, "name": "Same name"}}}


def test_repeat_import_and_same_name_different_ids(tmp_path):
    db = connect(tmp_path / "test.sqlite")
    audit = {"observed_at": "2026-10-21T13:09:37Z", "raw_files": [archive(tmp_path, [fixture()])]}
    ingest(db, audit, [1])
    before = report(db)
    ingest(db, audit, [1])
    assert before == report(db)
    assert before["entities"] == {"team": 2, "competition": 1, "fixture": 1}
    db.close()


def test_reschedule_and_rename_do_not_overwrite(tmp_path):
    db = connect(tmp_path / "test.sqlite")
    row = fixture()
    audit = {"observed_at": "2026-10-21T13:09:37Z", "raw_files": [archive(tmp_path, [row])]}
    ingest(db, audit, [1])
    row["fixture"]["date"] = "2026-10-23T00:00:00Z"
    row["teams"]["home"]["name"] = "New name"
    audit["raw_files"] = [archive(tmp_path, [row])]
    ingest(db, audit, [1])
    assert report(db)["observations"]["fixture"] == 2
    reasons = {r[0] for r in db.execute("SELECT reason FROM reviews")}
    assert {"fixture_changed", "name_conflict"} <= reasons
    assert db.execute("SELECT name FROM entities WHERE kind='team' AND provider_id='10'").fetchone()[0] == "Same name"
    db.close()


def test_membership_is_observation_not_transfer(tmp_path):
    db = connect(tmp_path / "test.sqlite")
    raw = archive(tmp_path, [fixture()])
    injury = {"fixture": {"id": 1}, "team": {"id": 10, "name": "Same name"},
              "player": {"id": 99, "name": "Player", "type": "Missing Fixture", "reason": "Unknown"}}
    audit = {"observed_at": "2026-10-21T13:09:37Z",
             "raw_files": [raw, archive(tmp_path, [injury], "injuries_2026-10-22")]}
    ingest(db, audit, [1])
    payload = json.loads(db.execute("SELECT payload FROM observations WHERE kind='membership_observation'").fetchone()[0])
    assert payload["valid_from"] is None and payload["valid_to"] is None
    assert report(db)["entities"]["player"] == 1
    db.close()


def test_invalid_archive_does_not_partially_import(tmp_path):
    db = connect(tmp_path / "test.sqlite")
    raw = archive(tmp_path, [fixture()])
    audit = {"observed_at": "2026-10-21T13:09:37Z", "raw_files": [raw]}
    from pathlib import Path
    Path(raw).write_text("{}")
    with pytest.raises(ValueError, match="digest"):
        ingest(db, audit, [1])
    assert report(db)["entities"] == {}
    db.close()
