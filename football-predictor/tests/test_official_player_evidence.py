import pytest

from data.entity_archive import connect, entity, observe
from data.official_player_evidence import import_official_evidence


def test_official_evidence_is_pending_idempotent_and_atomic(tmp_path):
    db = connect(tmp_path / "archive.sqlite3")
    eid = entity(db, "player", {"id": 1, "name": "Player"})
    team = entity(db, "team", {"id": 2, "name": "Club"})
    evidence = {"path": "manual.json", "sha256": "test", "observed_at": "2026-10-22T00:00:00+08:00"}
    observe(db, eid, "membership_observation", {"team_id": team}, evidence)
    db.commit()
    row = {"api_id": "1", "local_name": "Player", "team": "Club", "name": "Full Player",
           "birth_date": "2000-01-01", "url": "https://example.org/player", "association_basis": "manual check"}
    with pytest.raises(ValueError):
        import_official_evidence(db, [row, dict(row, team="Wrong")], evidence)
    assert db.execute("SELECT count(*) FROM observations WHERE kind='official_profile_candidate'").fetchone()[0] == 0
    import_official_evidence(db, [row], evidence)
    import_official_evidence(db, [row], evidence)
    assert db.execute("SELECT count(*) FROM observations WHERE kind='official_profile_candidate'").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM observations WHERE kind='player_profile'").fetchone()[0] == 0
    assert db.execute("SELECT status FROM reviews WHERE reason='official_profile_association'").fetchone()[0] == "pending"
    db.close()
